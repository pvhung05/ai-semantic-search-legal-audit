"""Tier2 so sanh noi dung: mot Dieu du thao vs cac Dieu me da duoc anh xa.

Prompt bo sung thong tin 'da sua boi'; validate dieu_me_id, trich_dan khop,
phan giai can_cu_khoan_id, phan loai vuot_tham_quyen theo cap.
Cache: tier2_cache theo hash_cap.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable

from psycopg import Connection
from rapidfuzz import fuzz

from app.doisanh.audit.consolidate import noi_dung_dieu_full
from app.doisanh.audit.focus_khoan import FocusKhoan, KhoanUngVien
from app.doisanh.audit.prompts import prompt_tier2, prompt_tier2_khoan
from app.doisanh.audit.segment import DonViSegment
from app.core.config import settings
from app.doisanh.db.repo_audit import cache_tier2_get, cache_tier2_set
from app.doisanh.ingestion.normalize import chuan_hoa_so_sanh
from app.core.models.llm import goi_json
from app.core.models.schemas import CanCu, PhatHien

LOAI_PHU_HOP = {"phu_hop"}
LOAI_HOP_LE = {
    "thu_hep_pham_vi", "mo_rong_pham_vi", "them_dieu_kien", "them_nghia_vu",
    "doi_so_lieu", "dat_thu_tuc_moi", "mau_thuan_truc_tiep", "vuot_tham_quyen",
}


def _cau_hinh_hash() -> str:
    cfg = f"{settings.LLM_MODEL}|{settings.LLM_TEMPERATURE}|{settings.AUDIT_MAX_TOKEN_PROMPT}"
    return hashlib.sha256(cfg.encode()).hexdigest()[:16]


def _hash_cap_cuc_bo(dv: DonViSegment, dieu_me_ids: list[str], ngay) -> str:
    key = (dv.hash + "|" + "|".join(sorted(dieu_me_ids)) + "|" + ngay.isoformat())
    return hashlib.sha256(key.encode()).hexdigest()


def _lay_dieu_me_payload(conn: Connection, dieu_me_ids: list[str]) -> list[dict]:
    out: list[dict] = []
    with conn.cursor() as cur:
        for dmid in dieu_me_ids:
            d = noi_dung_dieu_full(conn, dmid)
            if not d:
                continue
            cur.execute(
                "SELECT so_hieu, ten, cap FROM van_ban WHERE id=%s",
                (d["van_ban_id"],),
            )
            v = cur.fetchone()
            d["ten_vb"] = v[1] if v else ""
            d["so_hieu"] = v[0] if v else ""
            d["cap"] = v[2] if v else None
            d["da_sua_boi"] = bool(d.get("nguon_sua_doi_id"))
            out.append(d)
    return out


def _dong_du_thao(dv: DonViSegment, don_vi_list: list[DonViSegment]) -> dict:
    """Dong goi 1 Dieu + cac Khoan/Diem con cua no."""
    con = [c for c in don_vi_list if c.parent_id == dv.id
           or (c.parent_id and c.parent_id.startswith(dv.id + ":"))]
    return {
        "id": dv.id, "so_dieu": dv.so_dieu, "tieu_de": dv.tieu_de,
        "khoan": [
            {"so_khoan": c.so_khoan, "diem": c.diem, "noi_dung": c.noi_dung}
            for c in con if c.cap in {"khoan", "diem"}
        ],
    }


def _validate_phat_hien(
    item: dict, dv: DonViSegment, dieu_me_payload: list[dict],
) -> PhatHien | None:
    loai_loi = item.get("loai_loi")
    if loai_loi in LOAI_PHU_HOP:
        return None
    if loai_loi not in LOAI_HOP_LE:
        return None
    can_cu_raw = item.get("can_cu") or {}
    dieu_me_id = can_cu_raw.get("dieu_me_id")
    if not any(d["id"] == dieu_me_id for d in dieu_me_payload):
        return None  # bia can cu
    trich = (can_cu_raw.get("trich_dan") or "")[:1000]
    tin_cay = float(item.get("tin_cay") or 0.5)

    # Validate trich dan: fuzz partial >= 85 vs noi_dung Dieu me
    goc = next((d for d in dieu_me_payload if d["id"] == dieu_me_id), None)
    goc_text = (goc.get("noi_dung") or "") if goc else ""
    for k in (goc.get("khoan") or []):
        goc_text += "\n" + (k.get("noi_dung") or "")
    if trich and fuzz.partial_ratio(chuan_hoa_so_sanh(trich), chuan_hoa_so_sanh(goc_text)) < 85:
        tin_cay = min(tin_cay, 0.5)

    muc_do = item.get("muc_do") or "trung_binh"
    if muc_do not in {"cao", "trung_binh", "thap"}:
        muc_do = "trung_binh"

    return PhatHien(
        don_vi_id=dv.id, tang=2, loai_loi=loai_loi, muc_do=muc_do,
        tin_cay=tin_cay,
        can_cu=CanCu(
            dieu_me_id=dieu_me_id,
            van_ban_id=goc["van_ban_id"] if goc else None,
            so_khoan=can_cu_raw.get("so_khoan"),
            diem=can_cu_raw.get("diem"),
            trich_dan=trich,
        ),
        doan_du_thao=item.get("doan_du_thao") or dv.noi_dung[:400],
        giai_thich=item.get("giai_thich"),
        de_xuat_sua=item.get("de_xuat_sua"),
    )


def chay_tier2_cho_dieu(
    conn: Connection, dv: DonViSegment, don_vi_list: list[DonViSegment],
    dieu_me_ids: list[str], ngay, cap_du_thao: int | None,
    goi_json_fn: Callable[..., object] = goi_json,
) -> list[PhatHien]:
    """Chay tier2 cho 1 Dieu du thao, cac Dieu me da anh xa."""
    if not dieu_me_ids:
        return []
    hash_cap = _hash_cap_cuc_bo(dv, dieu_me_ids, ngay)
    cau_hinh = _cau_hinh_hash()
    cached = cache_tier2_get(conn, hash_cap, cau_hinh)
    if cached is not None:
        data = cached if isinstance(cached, list) else cached.get("items", [])
    else:
        dieu_me_payload = _lay_dieu_me_payload(conn, dieu_me_ids)
        cap_me_cao_nhat = max((d.get("cap") or 0) for d in dieu_me_payload) if dieu_me_payload else None
        messages = prompt_tier2(
            dieu_du_thao=_dong_du_thao(dv, don_vi_list),
            dieu_me_list=dieu_me_payload,
            cap_du_thao=cap_du_thao, cap_me_cao_nhat=cap_me_cao_nhat,
        )
        data = goi_json_fn(messages)
        if not isinstance(data, list):
            data = []
        cache_tier2_set(conn, hash_cap, cau_hinh, {"items": data})

    dieu_me_payload = _lay_dieu_me_payload(conn, dieu_me_ids)
    phat_hien: list[PhatHien] = []
    for item in data:
        p = _validate_phat_hien(item, dv, dieu_me_payload)
        if p is None:
            continue
        # vuot_tham_quyen: chi khi cap_du_thao > cap_me
        if p.loai_loi == "vuot_tham_quyen":
            goc_cap = next(
                (d.get("cap") for d in dieu_me_payload if d["id"] == (p.can_cu.dieu_me_id if p.can_cu else None)),
                None,
            )
            # cap VN: so nho = thu bac cao (HP=1, BL=2, ..., TT=7). du thao cap_tt THAP hon me
            # -> trai luat cap cao = mau_thuan_truc_tiep. vuot_tham_quyen = du thao cao hon me.
            if cap_du_thao is None or goc_cap is None or cap_du_thao >= goc_cap:
                p = p.model_copy(update={"loai_loi": "mau_thuan_truc_tiep"})
        phat_hien.append(p)
    return phat_hien


# ===================== TIER2 cap KHOAN (moi) =====================


def _hash_cap_khoan(dv: DonViSegment, khoan_ids: list[str], ngay) -> str:
    key = dv.hash + "|" + "|".join(sorted(khoan_ids)) + "|" + ngay.isoformat()
    return hashlib.sha256(key.encode()).hexdigest()


def _dong_khoan_du_thao(dv: DonViSegment) -> dict:
    return {
        "id": dv.id, "so_dieu": dv.so_dieu or "",
        "so_khoan": dv.so_khoan or "", "diem": dv.diem,
        "muc_cha": dv.tieu_de or "",  # tieu de Dieu/muc chua Khoan nay (ngu canh)
        "noi_dung": dv.noi_dung,
    }


def _dong_khoan_ung_vien(uv_list: list[KhoanUngVien]) -> list[dict]:
    rows: list[dict] = []
    for uv in uv_list:
        rows.append({
            "khoan_id": uv.khoan_id,
            "van_ban_id": uv.van_ban_id,
            "dieu_so": uv.so_dieu,
            "dieu_tieu_de": uv.tieu_de_dieu or "",
            "so_khoan": uv.so_khoan,
            "diem": uv.diem,
            "noi_dung": uv.noi_dung,
            "da_sua": uv.da_sua,
            "diem_tim_kiem": round(uv.diem_rrf, 4),
            "ngu_canh_truoc": uv.ngu_canh_truoc,
            "ngu_canh_sau": uv.ngu_canh_sau,
        })
    return rows


def _van_ban_cap(conn, van_ban_id: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT cap FROM van_ban WHERE id=%s", (van_ban_id,))
        r = cur.fetchone()
    return r[0] if r else None


def _validate_phat_hien_khoan(
    item: dict, dv: DonViSegment, uv_list: list[KhoanUngVien],
) -> PhatHien | None:
    loai_loi = item.get("loai_loi")
    if loai_loi in LOAI_PHU_HOP:
        return None
    if loai_loi not in LOAI_HOP_LE:
        return None
    can_cu_raw = item.get("can_cu") or {}
    khoan_id = can_cu_raw.get("khoan_id")
    uv_match = next((u for u in uv_list if u.khoan_id == khoan_id), None)
    if uv_match is None:
        return None  # LLM bia can_cu
    trich = (can_cu_raw.get("trich_dan") or "")[:1000]
    tin_cay = float(item.get("tin_cay") or 0.5)
    if trich and fuzz.partial_ratio(
        chuan_hoa_so_sanh(trich), chuan_hoa_so_sanh(uv_match.noi_dung),
    ) < 85:
        tin_cay = min(tin_cay, 0.5)
    muc_do = item.get("muc_do") or "trung_binh"
    if muc_do not in {"cao", "trung_binh", "thap"}:
        muc_do = "trung_binh"
    return PhatHien(
        don_vi_id=dv.id, tang=2, loai_loi=loai_loi, muc_do=muc_do,
        tin_cay=tin_cay,
        can_cu=CanCu(
            dieu_me_id=uv_match.dieu_id,
            van_ban_id=uv_match.van_ban_id,
            so_khoan=uv_match.so_khoan,
            diem=uv_match.diem,
            trich_dan=trich,
        ),
        doan_du_thao=item.get("doan_du_thao") or dv.noi_dung[:400],
        giai_thich=item.get("giai_thich"),
        de_xuat_sua=item.get("de_xuat_sua"),
    )


def chay_tier2_cho_khoan(
    conn: Connection, dv: DonViSegment, focus: FocusKhoan,
    ngay, cap_du_thao: int | None,
    goi_json_fn: Callable[..., object] = goi_json,
) -> list[PhatHien]:
    """Chay tier2 cho 1 Khoan/Diem du thao vs top-k Khoan me da focus."""
    if not focus.ung_vien:
        return []
    khoan_ids = [u.khoan_id for u in focus.ung_vien]
    hash_cap = _hash_cap_khoan(dv, khoan_ids, ngay)
    cau_hinh = _cau_hinh_hash()
    cached = cache_tier2_get(conn, hash_cap, cau_hinh)
    if cached is not None:
        data = cached if isinstance(cached, list) else cached.get("items", [])
    else:
        cap_me_cao_nhat = max(
            (_van_ban_cap(conn, u.van_ban_id) or 0) for u in focus.ung_vien
        ) if focus.ung_vien else None
        messages = prompt_tier2_khoan(
            doan_du_thao=_dong_khoan_du_thao(dv),
            khoan_ung_vien=_dong_khoan_ung_vien(focus.ung_vien),
            cap_du_thao=cap_du_thao, cap_me_cao_nhat=cap_me_cao_nhat,
        )
        data = goi_json_fn(messages)
        if not isinstance(data, list):
            if isinstance(data, dict):
                # Qwen co the goi trong 'items', 'phat_hien', 'ket_qua'
                for k in ("items", "phat_hien", "ket_qua", "data"):
                    if isinstance(data.get(k), list):
                        data = data[k]
                        break
                else:
                    data = []
            else:
                data = []
        cache_tier2_set(conn, hash_cap, cau_hinh, {"items": data})

    phat_hien: list[PhatHien] = []
    for item in data:
        p = _validate_phat_hien_khoan(item, dv, focus.ung_vien)
        if p is None:
            continue
        if p.loai_loi == "vuot_tham_quyen":
            goc = next((u for u in focus.ung_vien
                        if u.dieu_id == (p.can_cu.dieu_me_id if p.can_cu else None)), None)
            goc_cap = _van_ban_cap(conn, goc.van_ban_id) if goc else None
            # cap nho = thu bac cao. du thao cap LON hon (thap hon) ma trai = mau_thuan
            if cap_du_thao is None or goc_cap is None or cap_du_thao >= goc_cap:
                p = p.model_copy(update={"loai_loi": "mau_thuan_truc_tiep"})
        phat_hien.append(p)
    return phat_hien

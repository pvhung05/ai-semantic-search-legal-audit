"""Tier2 stateless: moi don vi du thao -> hybrid search toan kho -> LLM so sanh voi
top-k Khoan me -> verdict VI_PHAM/HOP_LE/CHUA_XAC_DINH. Tach khoi route."""
from __future__ import annotations

import concurrent.futures
import logging
from datetime import date
from typing import Any, Optional

from app.core.config import settings
from app.core.db.session import ket_noi
from app.core.models.llm import goi_json
from app.doisanh.audit.prompts import prompt_tier2_de_xuat, prompt_tier2_khoan
from app.doisanh.audit.validate import cat_theo_pham_vi, la_snippet_hop_le, vi_tri_can_cu
from app.doisanh.retrieval.can_cu import nap_khoan_ung_vien
from app.doisanh.retrieval.hybrid import tim_hybrid, tim_hybrid_tu_text

logger = logging.getLogger(__name__)


def parse_vec(s: str | None) -> list[float] | None:
    """pgvector tra ve dang text '[0.1,0.2,...]' -> list[float]. None neu rong."""
    if not s:
        return None
    s = s.strip().strip("[]")
    return [float(x) for x in s.split(",")] if s else None


def chunk_embed_text(dv) -> str:
    return (dv.tieu_de + ". " + dv.noi_dung) if dv.tieu_de else (dv.noi_dung or "")


def so_sanh_chunk(dv_dict: dict, ung_vien: list[dict], is_local: bool | None = None,
                  trich_yeu: str = "", think: bool | None = None) -> dict:
    """Pass 1: Goi LLM phan loai 1 chunk du thao voi top-k Khoan me (think=False mac dinh)."""
    if not ung_vien:
        return {}
    doan = {
        "id": dv_dict["id"], "so_dieu": dv_dict.get("so_dieu"),
        "so_khoan": dv_dict.get("so_khoan"), "diem": dv_dict.get("diem"),
        "tieu_de": dv_dict.get("tieu_de"), "noi_dung": dv_dict["noi_dung"],
    }
    uv_rut_gon = [
        {
            "khoan_id": u["khoan_id"], "so_hieu": u["so_hieu"],
            "ten_van_ban": u.get("ten_van_ban", ""),   # ten luat nguon -> LLM biet LINH VUC/domain
            "phan": u.get("phan"), "chuong": u.get("chuong"),
            "so_dieu": u["so_dieu"], "so_khoan": u["so_khoan"], "diem": u["diem"],
            "tieu_de_dieu": u["tieu_de_dieu"],
            "loai_rang_buoc": u.get("loai_rang_buoc", ["khong_ro"]),
            "noi_dung": u["noi_dung"][:2200],  # du cho khoi 'noi dung sau khi sua' o dau
        }
        for u in ung_vien
    ]
    messages = prompt_tier2_khoan(doan, uv_rut_gon, None, None, trich_yeu=trich_yeu)
    try:
        # Pass 1: luon tat thinking (think=False) de phan loai nhanh nhat
        data = goi_json(messages, is_local=is_local, think=False if think is None else think)
    except Exception as exc:
        logger.warning("LLM so sanh loi don_vi=%s: %s", dv_dict["id"], exc)
        return {}
    # LLM tra ve 1 object; phong truong hop tra list hoac boc trong 'ket_qua'
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict) and "trang_thai" not in data:
        inner = data.get("ket_qua") or data.get("items")
        if isinstance(inner, list) and inner:
            data = inner[0]
        elif isinstance(inner, dict):
            data = inner
    return data if isinstance(data, dict) else {}


def de_xuat_sua_chunk(
    dv_dict: dict,
    can_cu: dict,
    snippet_sai: str = "",
    ly_do_so_bo: str = "",
    is_local: bool | None = None,
    trich_yeu: str = "",
    think: bool | None = True,
) -> dict:
    """Pass 2: Goi LLM (think=True) suy luan va de xuat sua cho snippet vi pham."""
    messages = prompt_tier2_de_xuat(
        dv_dict, can_cu, snippet_sai=snippet_sai,
        ly_do_so_bo=ly_do_so_bo, trich_yeu=trich_yeu,
    )
    try:
        data = goi_json(messages, is_local=is_local, think=think)
    except Exception as exc:
        logger.warning("LLM de xuat sua loi don_vi=%s: %s", dv_dict.get("id"), exc)
        return {}
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict) and "de_xuat_sua" not in data:
        inner = data.get("ket_qua") or data.get("items")
        if isinstance(inner, list) and inner:
            data = inner[0]
        elif isinstance(inner, dict):
            data = inner
    return data if isinstance(data, dict) else {}


def _chuan_hoa_trang_thai(tt: str) -> str:
    tt = (tt or "").strip().lower()
    if tt in {"vi_pham", "vipham", "vi pham"}:
        return "VI_PHAM"
    if tt in {"hop_le", "hople", "hop le", "phu_hop"}:
        return "HOP_LE"
    return "CHUA_XAC_DINH"


def chay_tier2(don_vi_list: list, emb_by_id: dict, *, trich_yeu: str, ngay: date,
               van_ban_me_ids: Optional[list[str]],
               is_local: bool | None, think: bool | None = None) -> list[dict]:
    """Chay tier2 2-pass:
    - Pass 1: song song think=False phan loai nhanh VI_PHAM / HOP_LE / CHUA_XAC_DINH.
    - Pass 2: chi loc cac muc VI_PHAM dua qua think=True de suy luan va de xuat sua.
    """
    don_vi_can_xet = [dv for dv in don_vi_list if dv.cap in {"khoan", "diem", "doan"}]

    def _xu_ly(dv) -> tuple[Any, list[dict], dict]:
        # Truy van bang NOI DUNG thuan (embed tuoi), KHONG ghep tieu_de cha: tieu de keo
        # retrieval lech domain (ho so/thue/ngan hang) -> kem recall. Do thuc te: noi_dung
        # thuan lay duoc nhieu can cu dung linh vuc hon han. (Bo dung lai embedding da luu.)
        text = dv.noi_dung
        with ket_noi() as c:
            rows = tim_hybrid_tu_text(
                c, text, ngay=ngay, top_k=settings.RERANK_LAY_VE,
                van_ban_ids=van_ban_me_ids,
            )
            if not rows:
                return dv, [], {}
            diem_rrf = {r["chunk_id"]: r["diem_rrf"] for r in rows}
            ung_vien = nap_khoan_ung_vien(
                c, [r["chunk_id"] for r in rows], diem_rrf,
                query=text, top_n=settings.RERANK_TOP_N,
            )
        dv_dict = {
            "id": dv.id, "so_dieu": dv.so_dieu, "so_khoan": dv.so_khoan,
            "diem": dv.diem, "tieu_de": dv.tieu_de, "noi_dung": dv.noi_dung,
        }
        # Pass 1: luon think=False (hoac theo think neu nguoi dung truyen ro)
        kq_llm = so_sanh_chunk(dv_dict, ung_vien, is_local=is_local, trich_yeu=trich_yeu, think=think)
        return dv, ung_vien, kq_llm

    tier2_raw: list[tuple[Any, list[dict], dict]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.LLM_SONG_SONG) as pool:
        futs = {pool.submit(_xu_ly, dv): dv for dv in don_vi_can_xet}
        for fut in concurrent.futures.as_completed(futs):
            try:
                tier2_raw.append(fut.result())
            except Exception as exc:
                logger.exception("Chunk loi: %s", exc)

    # Pass 2: Loc cac vi pham, goi LLM voi think=True de suy luan va de xuat sua
    think_pass2 = False if think is False else True
    tasks_pass2 = []
    for dv, ung_vien, kq_llm in tier2_raw:
        if not ung_vien:
            continue
        if _chuan_hoa_trang_thai(kq_llm.get("trang_thai", "")) == "VI_PHAM":
            uv_map = {u["khoan_id"]: u for u in ung_vien}
            cc = kq_llm.get("can_cu") or {}
            u = uv_map.get(cc.get("khoan_id")) or ung_vien[0]
            snip = (kq_llm.get("noi_dung_du_thao") or "").strip() or dv.noi_dung
            dv_dict = {
                "id": dv.id, "so_dieu": dv.so_dieu, "so_khoan": dv.so_khoan,
                "diem": dv.diem, "tieu_de": dv.tieu_de, "noi_dung": dv.noi_dung,
            }
            tasks_pass2.append((kq_llm, dv_dict, u, snip))

            for loi in (kq_llm.get("cac_loi_them") or []):
                if isinstance(loi, dict):
                    snip2 = (loi.get("noi_dung_du_thao") or "").strip()
                    if snip2 and snip2 != snip:
                        u2 = uv_map.get(loi.get("khoan_id")) or u
                        tasks_pass2.append((loi, dv_dict, u2, snip2))

    if tasks_pass2:
        def _chay_p2(t):
            target_obj, dv_d, can_cu_u, snippet_s = t
            res = de_xuat_sua_chunk(
                dv_d, can_cu_u, snippet_sai=snippet_s,
                ly_do_so_bo=target_obj.get("giai_thich", ""),
                is_local=is_local, trich_yeu=trich_yeu, think=think_pass2,
            )
            if res.get("de_xuat_sua"):
                target_obj["de_xuat_sua"] = res["de_xuat_sua"]
            if res.get("giai_thich"):
                target_obj["giai_thich"] = res["giai_thich"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.LLM_SONG_SONG) as pool:
            list(pool.map(_chay_p2, tasks_pass2))

    tier2_kq: list[dict] = []
    for dv, ung_vien, kq_llm in tier2_raw:
        # Khong co ung vien nao -> chua co can cu
        if not ung_vien:
            tier2_kq.append({
                "don_vi_id": dv.id, "trang_thai": "CHUA_XAC_DINH",
                "doan_du_thao": dv.noi_dung,
                "so_hieu": "", "ten_van_ban": "", "trich_dan": "",
                "giai_thich": "Khong tim thay quy pham phap luat lien quan de doi chieu.",
                "de_xuat_sua": "", "tin_cay": 0.0,
            })
            continue
        trang_thai = _chuan_hoa_trang_thai(kq_llm.get("trang_thai", ""))
        cc = kq_llm.get("can_cu") or {}
        uv_map = {u["khoan_id"]: u for u in ung_vien}
        u = uv_map.get(cc.get("khoan_id")) or ung_vien[0]
        if trang_thai == "CHUA_XAC_DINH":
            tier2_kq.append({
                "don_vi_id": dv.id, "trang_thai": "CHUA_XAC_DINH",
                "doan_du_thao": dv.noi_dung,
                "so_hieu": "", "ten_van_ban": "", "trich_dan": "",
                "giai_thich": kq_llm.get("giai_thich")
                or "Noi dung du thao chua co can cu phap ly tuong ung.",
                "de_xuat_sua": "", "tin_cay": kq_llm.get("tin_cay", 0.0),
            })
        else:
            # VI_PHAM: dung snippet LLM chep (chi phan sai) neu hop le; nguoc lai nguyen van.
            snippet = (kq_llm.get("noi_dung_du_thao") or "").strip()
            dung_snippet = trang_thai == "VI_PHAM" and la_snippet_hop_le(snippet, dv.noi_dung)
            doan = snippet if dung_snippet else dv.noi_dung
            de_xuat = kq_llm.get("de_xuat_sua", "") if trang_thai == "VI_PHAM" else ""
            if dung_snippet:
                de_xuat = cat_theo_pham_vi(de_xuat, snippet, dv.noi_dung)
            tier2_kq.append({
                "don_vi_id": dv.id, "trang_thai": trang_thai,
                "doan_du_thao": doan,
                "so_hieu": u.get("so_hieu", ""),
                "ten_van_ban": u.get("ten_van_ban", ""),
                "trich_dan": cc.get("trich_dan") or u.get("noi_dung", ""),
                "giai_thich": kq_llm.get("giai_thich", ""),
                "de_xuat_sua": de_xuat,
                "tin_cay": kq_llm.get("tin_cay", 0.0),
                "tac_dong": u.get("tac_dong"),   # kem sua doi (neu co) de tra ra ket qua
                "cc_vi_tri": vi_tri_can_cu(u),  # vi tri can cu: Dieu X khoan Y
            })
            # Nhieu loi trong 1 don vi: moi loi phu -> 1 entry VI_PHAM rieng (tranh trung loi chinh)
            if trang_thai == "VI_PHAM":
                for loi in (kq_llm.get("cac_loi_them") or []):
                    if not isinstance(loi, dict):
                        continue
                    snip2 = (loi.get("noi_dung_du_thao") or "").strip()
                    if not snip2 or snip2 == snippet:
                        continue
                    u2 = uv_map.get(loi.get("khoan_id")) or u
                    ok2 = la_snippet_hop_le(snip2, dv.noi_dung)
                    dx2 = loi.get("de_xuat_sua", "")
                    if ok2:
                        dx2 = cat_theo_pham_vi(dx2, snip2, dv.noi_dung)
                    tier2_kq.append({
                        "don_vi_id": dv.id, "trang_thai": "VI_PHAM",
                        "doan_du_thao": snip2 if ok2 else dv.noi_dung,
                        "so_hieu": u2.get("so_hieu", ""),
                        "ten_van_ban": u2.get("ten_van_ban", ""),
                        "trich_dan": loi.get("trich_dan") or u2.get("noi_dung", ""),
                        "giai_thich": loi.get("giai_thich", ""),
                        "de_xuat_sua": dx2,
                        "tin_cay": kq_llm.get("tin_cay", 0.0),
                        "tac_dong": u2.get("tac_dong"),
                        "cc_vi_tri": vi_tri_can_cu(u2),
                    })
    return tier2_kq

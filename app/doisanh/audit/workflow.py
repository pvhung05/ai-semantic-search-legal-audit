"""Workflow doi chieu: tao -> cho_duyet_vb_me -> tier1 -> cho_duyet_anh_xa -> tier2 -> fallback -> xong.

Dung/duyet/tiep tuc qua `buoc` cua phien. tier2 chay song song theo Dieu.
Cap nhat thong_ke lien tuc.
"""
from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.doisanh.audit import mapping as mapping_mod
from app.doisanh.audit import parent_docs as pd_mod
from app.doisanh.audit import tier1 as tier1_mod
from app.doisanh.audit import tier2 as tier2_mod
from app.doisanh.audit.fallback import phat_hien_mo_coi_khong_can_cu, truy_hoi_dieu_mo_coi
from app.doisanh.audit.focus_khoan import focus_khoan as focus_khoan_fn
from app.doisanh.audit.segment import DonViSegment, segment_du_thao
from app.core.config import settings
from app.doisanh.db import repo_audit as ra
from app.doisanh.db import repo_tai_lieu as rt
from app.core.db.session import ket_noi
from app.doisanh.ingestion.loader import doc_file
from app.core.models.schemas import PhatHien

logger = logging.getLogger(__name__)


def _ghi_phat_hien(conn, phien_id: str, p: PhatHien, anh_xa_id: int | None = None) -> int:
    cc = p.can_cu
    return ra.luu_ket_qua(
        conn, phien_id, p.don_vi_id, p.tang, p.loai_loi, p.muc_do, p.tin_cay,
        anh_xa_id=anh_xa_id,
        can_cu_van_ban_id=cc.van_ban_id if cc else None,
        can_cu_dieu_id=cc.dieu_me_id if cc else None,
        can_cu_khoan_id=None,
        can_cu_trich_dan=cc.trich_dan if cc else None,
        doan_du_thao=p.doan_du_thao, giai_thich=p.giai_thich, de_xuat_sua=p.de_xuat_sua,
    )


def tao_phien_tu_du_thao(
    file_path: Path, loai_tai_lieu: str, ngay_du_kien: date,
    linh_vuc: list[str] | None = None, cap_tuong_duong: int | None = None,
    tu_dong_duyet: bool = False, che_do: str = "cay",
    ten: str | None = None,
) -> str:
    """Buoc 1: tao tai lieu, segment, tao phien, de xuat van ban me."""
    file_path = Path(file_path)
    text = doc_file(file_path)
    tai_lieu_id = rt.sinh_id_tai_lieu()
    file_hash = rt.hash_file(file_path)
    storage_key = rt.luu_file(file_path, tai_lieu_id)

    seg = segment_du_thao(text, tai_lieu_id)

    with ket_noi() as conn:
        rt.tao_tai_lieu(
            conn, tai_lieu_id,
            ten=ten or file_path.name,
            loai=loai_tai_lieu,
            cap_tuong_duong=cap_tuong_duong,
            ngay_du_kien=ngay_du_kien,
            linh_vuc=linh_vuc or [],
            can_cu_tho=seg.can_cu_tho,
            co_cau_truc_dieu=seg.co_cau_truc_dieu,
            storage_key=storage_key, file_hash=file_hash,
        )
        for dv in seg.don_vi:
            rt.luu_don_vi(conn, {
                "id": dv.id, "tai_lieu_id": tai_lieu_id, "parent_id": dv.parent_id,
                "cap": dv.cap, "so_dieu": dv.so_dieu, "so_khoan": dv.so_khoan,
                "diem": dv.diem, "tieu_de": dv.tieu_de,
                "noi_dung": dv.noi_dung, "hash": dv.hash, "thu_tu": dv.thu_tu,
            })

        phien_id = ra.tao_phien(conn, tai_lieu_id, ngay_du_kien, che_do, tu_dong_duyet)
        pd = pd_mod.de_xuat_van_ban_me(
            conn, tai_lieu_id, loai_tai_lieu, linh_vuc or [], seg.can_cu_tho,
        )
        for dx in pd.de_xuat:
            ra.luu_van_ban_me(conn, phien_id, dx.van_ban_id, dx.nguon, dx.buoc_sau, "de_xuat")
        with conn.cursor() as cur:
            cur.execute("UPDATE tai_lieu SET loai_cay=%s WHERE id=%s",
                        (pd.loai_cay, tai_lieu_id))
        if tu_dong_duyet:
            ra.duyet_van_ban_me(conn, phien_id,
                                [dx.van_ban_id for dx in pd.de_xuat], "chap_nhan")
            ra.cap_nhat_buoc(conn, phien_id, "tier1")
        else:
            ra.cap_nhat_buoc(conn, phien_id, "cho_duyet_vb_me")
        conn.commit()
    return phien_id


def tiep_tuc(phien_id: str) -> dict:
    """Thuc hien tu buoc hien tai den khi cho_duyet/xong."""
    with ket_noi() as conn:
        ph = ra.lay_phien(conn, phien_id)
    if ph is None:
        return {"phien_id": phien_id, "trang_thai": "khong_ton_tai"}

    buoc = ph["buoc"]
    tu_dong = ph["tu_dong_duyet"]

    if buoc == "cho_duyet_vb_me":
        return {"phien_id": phien_id, "buoc": buoc,
                "ghi_chu": "Can duyet van ban me truoc khi tiep tuc"}
    if buoc in {"tao"}:
        return {"phien_id": phien_id, "buoc": buoc, "ghi_chu": "Phien chua san sang"}

    thong_ke = ph["thong_ke"] or {}
    try:
        if buoc in {"tier1", "chap_nhan_vb_me"}:
            thong_ke.update(_chay_tier1(conn, ph))
            # Flow moi (cap Khoan + focus embedding): bo qua mapping LLM, di thang sang tier2
            buoc_tiep = "tier2" if tu_dong else "cho_duyet_anh_xa"
            if not tu_dong:
                try:
                    _chay_mapping_khi_chua_chay(conn, ph, thong_ke)
                except Exception as exc:
                    logger.warning("mapping LLM loi, bo qua: %s", exc)
            with ket_noi() as conn2:
                ra.cap_nhat_buoc(conn2, phien_id, buoc_tiep, thong_ke=thong_ke)
                conn2.commit()
            if buoc_tiep == "cho_duyet_anh_xa":
                return {"phien_id": phien_id, "buoc": buoc_tiep, "thong_ke": thong_ke}
            buoc = buoc_tiep

        if buoc == "cho_duyet_anh_xa":
            return {"phien_id": phien_id, "buoc": buoc,
                    "ghi_chu": "Can duyet anh xa truoc khi tiep tuc"}

        if buoc == "tier2":
            thong_ke.update(_chay_tier2(conn, ph))
            with ket_noi() as conn2:
                ra.cap_nhat_buoc(conn2, phien_id, "fallback", thong_ke=thong_ke)
                conn2.commit()
            buoc = "fallback"

        if buoc == "fallback":
            thong_ke.update(_chay_fallback(conn, ph))
            with ket_noi() as conn2:
                ra.cap_nhat_buoc(conn2, phien_id, "xong", thong_ke=thong_ke)
                conn2.commit()
            return {"phien_id": phien_id, "buoc": "xong", "thong_ke": thong_ke}

        return {"phien_id": phien_id, "buoc": buoc, "thong_ke": thong_ke}
    except Exception as exc:
        logger.exception("Workflow loi")
        with ket_noi() as conn2:
            ra.cap_nhat_buoc(conn2, phien_id, "loi", loi=str(exc), thong_ke=thong_ke)
            conn2.commit()
        return {"phien_id": phien_id, "buoc": "loi", "loi": str(exc)}


def _lay_don_vi_list(conn, tai_lieu_id: str) -> list[DonViSegment]:
    rows = rt.danh_sach_don_vi(conn, tai_lieu_id)
    return [DonViSegment(
        id=r["id"], cap=r["cap"], so_dieu=r["so_dieu"], so_khoan=r["so_khoan"],
        diem=r["diem"], tieu_de=r["tieu_de"], noi_dung=r["noi_dung"],
        hash=r["hash"], thu_tu=r["thu_tu"], parent_id=r["parent_id"],
    ) for r in rows]


def _chay_tier1(conn, ph: dict) -> dict:
    with ket_noi() as c:
        don_vi = _lay_don_vi_list(c, ph["tai_lieu_id"])
        with c.cursor() as cur:
            cur.execute("SELECT can_cu_tho, cap_tuong_duong FROM tai_lieu WHERE id=%s",
                        (ph["tai_lieu_id"],))
            r = cur.fetchone()
        can_cu_tho = (r[0] if r else []) or []
        cap_tai_lieu = r[1] if r else None
        van_ban_me = [v["van_ban_id"] for v in ra.danh_sach_van_ban_me(c, ph["id"], duyet="chap_nhan")]
        phat_hien = tier1_mod.chay_tier1(c, don_vi, ph["ngay_tra"], van_ban_me, can_cu_tho, cap_tai_lieu)
        so = 0
        for p in phat_hien:
            _ghi_phat_hien(c, ph["id"], p)
            so += 1
        c.commit()
    return {"tier1_phat_hien": so}


def _chay_mapping(conn, ph: dict) -> dict:
    with ket_noi() as c:
        don_vi = _lay_don_vi_list(c, ph["tai_lieu_id"])
        van_ban_me = [v["van_ban_id"] for v in ra.danh_sach_van_ban_me(c, ph["id"], duyet="chap_nhan")]
        anh_xa_list = mapping_mod.anh_xa_dieu(c, don_vi, van_ban_me, ph["ngay_tra"])
        for ax in anh_xa_list:
            if not ax["dieu_me_ids"]:
                ra.luu_anh_xa(c, ph["id"], ax["don_vi_id"], None,
                              "khong", ax["tin_cay"], ax["nguon"], duyet="chap_nhan")
                continue
            for dmid in ax["dieu_me_ids"]:
                ra.luu_anh_xa(c, ph["id"], ax["don_vi_id"], dmid,
                              ax["loai"], ax["tin_cay"], ax["nguon"],
                              duyet="chap_nhan" if ph["tu_dong_duyet"] else "de_xuat")
        c.commit()
    return {"mapping_so_dieu": len(anh_xa_list)}


def _chay_mapping_khi_chua_chay(conn, ph: dict, thong_ke: dict) -> None:
    """Khi tu_dong_duyet=false: van tao anh_xa de nguoi dung duyet."""
    with ket_noi() as c:
        existed = ra.danh_sach_anh_xa(c, ph["id"])
    if existed:
        return
    thong_ke.update(_chay_mapping(conn, ph))


def _chay_tier2(conn, ph: dict) -> dict:
    """Tier2 cap Khoan: moi Khoan/Diem/doan du thao -> focus top-k Khoan me -> LLM so sanh.

    Dung VB me da duyet (khong qua anh_xa_dieu nua) -> focus_khoan tu loc Khoan.
    """
    with ket_noi() as c:
        don_vi = _lay_don_vi_list(c, ph["tai_lieu_id"])
        van_ban_me = [v["van_ban_id"]
                      for v in ra.danh_sach_van_ban_me(c, ph["id"], duyet="chap_nhan")]
        with c.cursor() as cur:
            cur.execute("SELECT cap_tuong_duong FROM tai_lieu WHERE id=%s", (ph["tai_lieu_id"],))
            cap = cur.fetchone()[0]

    if not van_ban_me:
        return {"tier2_phat_hien": 0, "tier2_so_khoan": 0, "ghi_chu": "khong co VB me da duyet"}

    don_vi_can_xet = [dv for dv in don_vi if dv.cap in {"khoan", "diem", "doan"}]

    # Focus Khoan: 1 goi 1 lan cho tat ca
    with ket_noi() as c2:
        fks = focus_khoan_fn(
            c2, don_vi_can_xet, van_ban_me_ids=van_ban_me,
            ngay=ph["ngay_tra"], top_k=5,
        )
    focus_map = {fk.don_vi_id: fk for fk in fks}

    # Chay LLM tier2 song song theo Khoan
    so_vi_pham = 0
    so_hop_le = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.LLM_SONG_SONG) as pool:
        futures = {}
        for dv in don_vi_can_xet:
            fk = focus_map.get(dv.id)
            if fk is None or not fk.ung_vien:
                continue
            def _run(dv=dv, fk=fk):
                with ket_noi() as c3:
                    return tier2_mod.chay_tier2_cho_khoan(c3, dv, fk, ph["ngay_tra"], cap)
            futures[pool.submit(_run)] = dv.id
        don_vi_map = {dv.id: dv for dv in don_vi_can_xet}
        with ket_noi() as c4:
            for fut, dv_id in futures.items():
                try:
                    phat_hien = fut.result()
                except Exception as exc:
                    logger.exception("tier2 Khoan loi %s: %s", dv_id, exc)
                    continue
                dv = don_vi_map[dv_id]
                fk = focus_map[dv_id]
                if phat_hien:
                    for p in phat_hien:
                        _ghi_phat_hien(c4, ph["id"], p)
                        so_vi_pham += 1
                else:
                    # HOP_LE: ghi 1 ban can cu Khoan me top-1 cho nguoi dung xem
                    uv_top = fk.ung_vien[0]
                    p_hop_le = _tao_phat_hien_hop_le(dv, uv_top)
                    _ghi_phat_hien(c4, ph["id"], p_hop_le)
                    so_hop_le += 1
            c4.commit()
    return {
        "tier2_phat_hien": so_vi_pham,
        "tier2_hop_le": so_hop_le,
        "tier2_so_khoan": len(futures),
    }


def _tao_phat_hien_hop_le(dv, uv_top) -> "PhatHien":
    """Ghi 1 record HOP_LE voi can cu Khoan me top-1 de nguoi dung so sanh."""
    from app.core.models.schemas import CanCu, PhatHien
    return PhatHien(
        don_vi_id=dv.id, tang=2, loai_loi="phu_hop",
        muc_do="thap", tin_cay=uv_top.diem_rrf,
        can_cu=CanCu(
            dieu_me_id=uv_top.dieu_id,
            van_ban_id=uv_top.van_ban_id,
            so_khoan=uv_top.so_khoan, diem=uv_top.diem,
            trich_dan=uv_top.noi_dung,
        ),
        doan_du_thao=dv.noi_dung,
        giai_thich=(
            f"He thong so sanh Khoan du thao voi {uv_top.van_ban_id} "
            f"Dieu {uv_top.so_dieu} Khoan {uv_top.so_khoan}: khong thay vi pham ro rang."
        ),
    )


def _chay_fallback(conn, ph: dict) -> dict:
    """Tat fallback: Khoan khong co phat hien = HOP_LE (im lang).

    Khi `ENABLE_FALLBACK=true` co the mo lai de truy hoi hybrid (GD E).
    """
    return {"fallback_mo_coi": 0}


def duyet_vb_me(phien_id: str, van_ban_ids: list[str], duyet: str = "chap_nhan") -> None:
    with ket_noi() as conn:
        ra.duyet_van_ban_me(conn, phien_id, van_ban_ids, duyet)
        if duyet == "chap_nhan":
            ra.cap_nhat_buoc(conn, phien_id, "tier1")
        conn.commit()


def duyet_anh_xa(phien_id: str, anh_xa_updates: list[dict]) -> None:
    """Cap nhat duyet / sua anh xa; sau do chuyen sang tier2."""
    with ket_noi() as conn, conn.cursor() as cur:
        for u in anh_xa_updates:
            cur.execute(
                "UPDATE anh_xa_dieu SET duyet=%s WHERE id=%s",
                (u["duyet"], u["id"]),
            )
        ra.cap_nhat_buoc(conn, phien_id, "tier2")
        conn.commit()

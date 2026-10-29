"""Tier1 kiem tra xac dinh (khong LLM): dan chieu, hieu luc, nguyen van, the thuc."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from psycopg import Connection
from rapidfuzz import fuzz

from app.audit.segment import DonViSegment
from app.config import settings
from app.db.repo_hieu_luc import dieu_hieu_luc_tai, khoan_hieu_luc_tai
from app.ingestion.citation_parser import trich_dan_chieu
from app.ingestion.normalize import chuan_hoa_so_sanh
from app.models.schemas import DanChieu, PhatHien, CanCu

RE_TRICH = re.compile(r'"([^"\n]{20,})"')
RE_SAU_QUY_DINH = re.compile(r"quy định[:\s]+(.{20,}?)(?=[\.;\n]|$)", re.IGNORECASE)


def _phat_hien_dan_chieu_khoan(
    conn: Connection, dv: DonViSegment, dc: DanChieu, ngay: date, van_ban_me_ids: list[str],
) -> PhatHien | None:
    """Phat hien loi dan chieu: khong_ton_tai | sai_so_hieu | het_hieu_luc | bai_bo | chua_hieu_luc."""
    van_ban_id: str | None = None
    if dc.la_noi_bo:
        return None  # dan chieu noi bo du thao -> khong kiem o tier1
    if dc.so_hieu:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (dc.so_hieu,))
            row = cur.fetchone()
            van_ban_id = row[0] if row else None
    if van_ban_id is None:
        return PhatHien(
            don_vi_id=dv.id, tang=1,
            loai_loi="dan_chieu_sai_so_hieu" if dc.so_hieu else "dan_chieu_khong_ton_tai",
            muc_do="cao", tin_cay=1.0,
            doan_du_thao=dc.text_dan,
            can_cu=CanCu(trich_dan=f"Khong tim thay van ban so_hieu={dc.so_hieu}"),
            giai_thich=f"Khong co van ban khop so hieu '{dc.so_hieu}' trong kho.",
            de_xuat_sua="Kiem tra lai so hieu van ban hoac bo dan chieu.",
        )
    if dc.so_dieu is None:
        return None
    if dc.so_khoan is None:
        d = dieu_hieu_luc_tai(conn, van_ban_id, dc.so_dieu, ngay)
        if d is None:
            # Thu tim bat ke trang thai
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, trang_thai FROM dieu_luat WHERE van_ban_id=%s AND so_dieu=%s "
                    "ORDER BY hieu_luc_tu DESC NULLS LAST LIMIT 1",
                    (van_ban_id, dc.so_dieu),
                )
                row = cur.fetchone()
            if row is None:
                return PhatHien(
                    don_vi_id=dv.id, tang=1, loai_loi="dan_chieu_khong_ton_tai",
                    muc_do="cao", tin_cay=1.0, doan_du_thao=dc.text_dan,
                    giai_thich=f"Dieu {dc.so_dieu} khong ton tai trong {dc.so_hieu}.",
                )
            tt = row[1]
            loai = {
                "bai_bo": "dan_bi_bai_bo",
                "het_hieu_luc": "dan_het_hieu_luc",
            }.get(tt, "dan_chieu_khong_ton_tai")
            return PhatHien(
                don_vi_id=dv.id, tang=1, loai_loi=loai, muc_do="cao", tin_cay=1.0,
                doan_du_thao=dc.text_dan,
                can_cu=CanCu(dieu_me_id=row[0], van_ban_id=van_ban_id),
                giai_thich=f"Dieu {dc.so_dieu} trong {dc.so_hieu} co trang thai '{tt}' tai ngay {ngay}.",
            )
        return None
    k = khoan_hieu_luc_tai(conn, van_ban_id, dc.so_dieu, dc.so_khoan, dc.diem, ngay)
    if k is None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT k.id, k.trang_thai FROM khoan k JOIN dieu_luat d ON d.id=k.dieu_id "
                "WHERE k.van_ban_id=%s AND d.so_dieu=%s AND k.so_khoan=%s "
                "AND ((k.diem IS NULL AND %s IS NULL) OR k.diem=%s) "
                "ORDER BY k.hieu_luc_tu DESC NULLS LAST LIMIT 1",
                (van_ban_id, dc.so_dieu, dc.so_khoan, dc.diem, dc.diem),
            )
            row = cur.fetchone()
        if row is None:
            return PhatHien(
                don_vi_id=dv.id, tang=1, loai_loi="dan_chieu_khong_ton_tai",
                muc_do="cao", tin_cay=1.0, doan_du_thao=dc.text_dan,
                giai_thich=f"Khoan {dc.so_khoan} Dieu {dc.so_dieu} khong ton tai.",
            )
        tt = row[1]
        loai = {"bai_bo": "dan_bi_bai_bo", "het_hieu_luc": "dan_het_hieu_luc"}.get(
            tt, "dan_chieu_khong_ton_tai",
        )
        return PhatHien(
            don_vi_id=dv.id, tang=1, loai_loi=loai, muc_do="cao", tin_cay=1.0,
            doan_du_thao=dc.text_dan,
            can_cu=CanCu(van_ban_id=van_ban_id, so_khoan=dc.so_khoan, diem=dc.diem),
            giai_thich=f"Khoan {dc.so_khoan} Dieu {dc.so_dieu} co trang thai '{tt}' tai {ngay}.",
        )
    return None


def _kiem_trich_nguyen_van(
    conn: Connection, dv: DonViSegment, dc: DanChieu, ngay: date, trich: str,
) -> PhatHien | None:
    """Dieu/Khoan dan chieu + trich -> fuzz voi noi dung thuc."""
    if dc.la_noi_bo or not dc.so_dieu or not dc.so_hieu:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (dc.so_hieu,))
        row = cur.fetchone()
    if row is None:
        return None
    van_ban_id = row[0]
    goc: str | None = None
    if dc.so_khoan:
        k = khoan_hieu_luc_tai(conn, van_ban_id, dc.so_dieu, dc.so_khoan, dc.diem, ngay)
        goc = k.get("noi_dung") if k else None
    else:
        d = dieu_hieu_luc_tai(conn, van_ban_id, dc.so_dieu, ngay)
        goc = d.get("noi_dung") if d else None
    if not goc:
        return None
    ratio = fuzz.ratio(chuan_hoa_so_sanh(trich), chuan_hoa_so_sanh(goc))
    nguong = settings.AUDIT_DIFF_NGUONG * 100
    if ratio >= nguong:
        return None
    return PhatHien(
        don_vi_id=dv.id, tang=1, loai_loi="trich_sai_nguyen_van",
        muc_do="trung_binh", tin_cay=1.0,
        doan_du_thao=trich,
        can_cu=CanCu(van_ban_id=van_ban_id, trich_dan=goc[:400]),
        giai_thich=f"Trich khong khop (ratio={ratio:.1f}%, nguong={nguong:.0f}%).",
        de_xuat_sua=f"Dung nguyen van: \"{goc[:200]}...\"",
    )


def _kiem_the_thuc_can_cu(
    conn: Connection, can_cu_tho: list[str], cap_tai_lieu: int | None,
    don_vi_anchor_id: str,
) -> list[PhatHien]:
    """So hieu trong can cu khong khop loai/co quan/trang thai -> the_thuc.
    Gan vao don_vi_anchor_id (thuong la don vi dau tien cua du thao).
    """
    kq: list[PhatHien] = []
    from app.ingestion.quan_he import RE_SO_HIEU
    for dong in can_cu_tho:
        for sh in RE_SO_HIEU.findall(dong):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, loai, cap, trang_thai FROM van_ban WHERE so_hieu=%s",
                    (sh,),
                )
                row = cur.fetchone()
            if row is None:
                kq.append(PhatHien(
                    don_vi_id=don_vi_anchor_id, tang=1, loai_loi="the_thuc",
                    muc_do="trung_binh", tin_cay=1.0,
                    doan_du_thao=dong,
                    giai_thich=f"[Can cu] So hieu '{sh}' chua co trong kho.",
                ))
                continue
            vb_id, vb_loai, vb_cap, vb_trang_thai = row
            if vb_trang_thai in {"het_hieu_luc", "het_hieu_luc_mot_phan"}:
                kq.append(PhatHien(
                    don_vi_id=don_vi_anchor_id, tang=1, loai_loi="dan_het_hieu_luc",
                    muc_do="cao", tin_cay=1.0,
                    doan_du_thao=dong,
                    giai_thich=f"[Can cu] Van ban {sh} ({vb_id}) trang thai {vb_trang_thai}.",
                    de_xuat_sua="Thay bang van ban moi con hieu luc.",
                ))
    return kq


def chay_tier1(
    conn: Connection, don_vi_list: list[DonViSegment], ngay: date,
    van_ban_me_ids: list[str], can_cu_tho: list[str] | None = None,
    cap_tai_lieu: int | None = None,
) -> list[PhatHien]:
    """Chay tier1 cho moi don vi cap khoan|diem|doan|cum."""
    phat_hien: list[PhatHien] = []
    for dv in don_vi_list:
        if dv.cap not in {"khoan", "diem", "doan", "cum"}:
            continue
        dcs = trich_dan_chieu(dv.noi_dung or "")
        for dc in dcs:
            p = _phat_hien_dan_chieu_khoan(conn, dv, dc, ngay, van_ban_me_ids)
            if p:
                phat_hien.append(p)
            for m in RE_TRICH.finditer(dv.noi_dung or ""):
                trich = m.group(1)
                p2 = _kiem_trich_nguyen_van(conn, dv, dc, ngay, trich)
                if p2:
                    phat_hien.append(p2)
            for m in RE_SAU_QUY_DINH.finditer(dv.noi_dung or ""):
                p2 = _kiem_trich_nguyen_van(conn, dv, dc, ngay, m.group(1))
                if p2:
                    phat_hien.append(p2)
    if can_cu_tho and don_vi_list:
        anchor = don_vi_list[0].id
        phat_hien.extend(_kiem_the_thuc_can_cu(conn, can_cu_tho, cap_tai_lieu, anchor))
    return phat_hien

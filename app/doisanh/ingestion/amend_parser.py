"""Parse van ban sua doi -> list[LenhSuaDoi] va luu vao quan_he_van_ban.

Nguyen tac:
- Moi Khoan trong Dieu "Sua doi, bo sung mot so dieu cua ..." la mot lenh.
- Pattern: sua_doi | bo_sung | bai_bo | thay_cum_tu.
- Khong khop -> ghi lenh tho tin_cay='can_ra_soat' + canh bao.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from psycopg import Connection

from app.core.models.schemas import LenhSuaDoi, VanBanParsed

logger = logging.getLogger(__name__)

RE_SUA_DOI_KHOAN = re.compile(
    r"Sửa đổi(?:,?\s*bổ sung)?\s+(?:Khoản\s+(\d+[a-zđ]?)\s+)?Điều\s+(\d+[a-zđ]?)",
    re.IGNORECASE,
)
RE_BO_SUNG = re.compile(
    r"Bổ sung\s+(?:Khoản\s+(\d+[a-zđ]?)\s+)?(?:vào\s+)?(?:sau|trước)?\s*(?:Khoản\s+(\d+[a-zđ]?)\s+)?Điều\s+(\d+[a-zđ]?)",
    re.IGNORECASE,
)
RE_BAI_BO = re.compile(
    r"Bãi bỏ\s+(?:Khoản\s+(\d+[a-zđ]?)\s+)?Điều\s+(\d+[a-zđ]?)",
    re.IGNORECASE,
)
RE_THAY_CUM_TU = re.compile(
    r"Thay(?: thế)? cụm từ\s+\"([^\"]+)\"\s+bằng\s+\"([^\"]+)\"",
    re.IGNORECASE,
)
RE_VI_TRI = re.compile(r"\b(sau|trước)\b", re.IGNORECASE)
RE_SO_HIEU = re.compile(r"(\d+/\d+/[A-ZĐ0-9\-]+)")


def _dich_so_hieu(noi_dung_tieu_de: str) -> str | None:
    """Rut so hieu van ban dich tu tieu de Dieu 'Sua doi, bo sung ... cua NDxx/202x'."""
    m = RE_SO_HIEU.search(noi_dung_tieu_de or "")
    return m.group(1) if m else None


def _lenh_tho(noi_dung: str, nguon_lenh: str, dich_so_hieu: str | None) -> LenhSuaDoi:
    return LenhSuaDoi(
        loai="sua_doi",
        dich_so_hieu=dich_so_hieu,
        noi_dung_moi=noi_dung,
        nguon_lenh=nguon_lenh,
        tin_cay="can_ra_soat",
    )


def parse_lenh_sua_doi(parsed: VanBanParsed) -> list[LenhSuaDoi]:
    """Rut lenh sua doi tu moi Khoan cua Dieu nhan dang la sua doi."""
    lenh: list[LenhSuaDoi] = []
    for d in parsed.dieu:
        tieu_de_dieu = d.tieu_de or ""
        if not (
            "Sửa đổi" in tieu_de_dieu or "Bổ sung" in tieu_de_dieu
            or "sửa đổi" in tieu_de_dieu or "bổ sung" in tieu_de_dieu
        ):
            continue
        dich_so_hieu = _dich_so_hieu(tieu_de_dieu + " " + (d.noi_dung or "")[:200])
        for k in d.khoan:
            if k.diem is not None:
                continue  # Diem thuoc Khoan cha, bo qua
            noi_dung = k.noi_dung
            nguon = f"D{d.so_dieu}:K{k.so_khoan}"
            l = _thu_khop_lenh(noi_dung, nguon, dich_so_hieu)
            if l is None:
                logger.warning("Lenh khong khop pattern: %s - %s", nguon, noi_dung[:80])
                lenh.append(_lenh_tho(noi_dung, nguon, dich_so_hieu))
            else:
                lenh.append(l)
    return lenh


def _thu_khop_lenh(
    noi_dung: str, nguon_lenh: str, dich_so_hieu: str | None
) -> LenhSuaDoi | None:
    # thu_cum_tu
    m = RE_THAY_CUM_TU.search(noi_dung)
    if m:
        return LenhSuaDoi(
            loai="thay_cum_tu",
            dich_so_hieu=dich_so_hieu,
            cum_tu_cu=m.group(1), cum_tu_moi=m.group(2),
            noi_dung_moi=None,
            nguon_lenh=nguon_lenh,
            tin_cay="can_ra_soat",
        )
    # bai_bo
    m = RE_BAI_BO.search(noi_dung)
    if m:
        return LenhSuaDoi(
            loai="bai_bo",
            dich_so_hieu=dich_so_hieu,
            dich_so_khoan=m.group(1), dich_so_dieu=m.group(2),
            nguon_lenh=nguon_lenh, tin_cay="can_ra_soat",
        )
    # bo_sung
    m = RE_BO_SUNG.search(noi_dung)
    if m:
        vi_tri = None
        mvt = RE_VI_TRI.search(noi_dung[: m.end() + 30] if m else "")
        if mvt:
            vi_tri = "sau" if mvt.group(1).lower().startswith("sau") else "truoc"
        return LenhSuaDoi(
            loai="bo_sung",
            dich_so_hieu=dich_so_hieu,
            dich_so_khoan=m.group(1) or m.group(2),
            dich_so_dieu=m.group(3),
            vi_tri=vi_tri,
            noi_dung_moi=noi_dung,
            nguon_lenh=nguon_lenh,
            tin_cay="can_ra_soat",
        )
    # sua_doi
    m = RE_SUA_DOI_KHOAN.search(noi_dung)
    if m:
        return LenhSuaDoi(
            loai="sua_doi",
            dich_so_hieu=dich_so_hieu,
            dich_so_khoan=m.group(1), dich_so_dieu=m.group(2),
            noi_dung_moi=noi_dung,
            nguon_lenh=nguon_lenh, tin_cay="can_ra_soat",
        )
    return None


def _tim_dich_van_ban_id(conn: Connection, so_hieu: str | None) -> str | None:
    if not so_hieu:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (so_hieu,))
        row = cur.fetchone()
    return row[0] if row else None


def luu_lenh_sua_doi(
    conn: Connection, nguon_van_ban_id: str, lenh_list: list[LenhSuaDoi]
) -> int:
    """Ghi tung lenh vao quan_he_van_ban. Chua phan giai dich_dieu_id/dich_khoan_id (ap dung o sync)."""
    so = 0
    with conn.cursor() as cur:
        for l in lenh_list:
            dich_id = _tim_dich_van_ban_id(conn, l.dich_so_hieu)
            if dich_id is None:
                logger.warning(
                    "Chua tim duoc van ban dich cho so_hieu=%s (lenh %s); bo qua",
                    l.dich_so_hieu, l.nguon_lenh,
                )
                continue
            cur.execute(
                """
                INSERT INTO quan_he_van_ban (
                  nguon_id, dich_id, loai, dich_so_dieu, dich_so_khoan, dich_diem,
                  vi_tri, ngay_hieu_luc, noi_dung_moi,
                  cum_tu_cu, cum_tu_moi, nguon_lenh, tin_cay, da_ap_dung
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
                """,
                (
                    nguon_van_ban_id, dich_id, l.loai,
                    l.dich_so_dieu, l.dich_so_khoan, l.dich_diem,
                    l.vi_tri, l.ngay_hieu_luc, l.noi_dung_moi,
                    l.cum_tu_cu, l.cum_tu_moi, l.nguon_lenh, l.tin_cay,
                ),
            )
            so += 1
    return so

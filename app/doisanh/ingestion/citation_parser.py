"""Trich dan chieu phap ly trong text:

Pattern (muc 6.2):
  (điểm X )?(khoản N )?Điều M (của )?(Luật này|Bộ luật này|Nghị định này|Thông tư này|<ten/so hieu>)

- "Luat nay" = van ban chua Khoan goc.
- Nhieu Dieu -> nhieu dong.
"""
from __future__ import annotations

import re
from typing import Iterable

from psycopg import Connection

from app.core.models.schemas import DanChieu

RE_NOI_BO = re.compile(
    r"(?:(điểm|Điểm)\s+([a-zđ])\s+)?"
    r"(?:(khoản|Khoản)\s+(\d+[a-zđ]?)\s+)?"
    r"(Điều|điều)\s+(\d+[a-zđ]?)\s+"
    r"(?:của\s+)?(Luật này|Bộ luật này|Nghị định này|Thông tư này|Hiến pháp này)",
    re.IGNORECASE,
)
RE_NGOAI = re.compile(
    r"(?:(điểm|Điểm)\s+([a-zđ])\s+)?"
    r"(?:(khoản|Khoản)\s+(\d+[a-zđ]?)\s+)?"
    r"(Điều|điều)\s+(\d+[a-zđ]?)\s+"
    r"(?:của\s+)?"
    r"((?:Luật|Bộ luật|Nghị định|Thông tư|Hiến pháp|Nghị quyết|Quyết định)[^.;,\n]{0,120}?"
    r"(?:số\s+(\d+/\d+/[A-ZĐ\-]+)|năm\s+\d{4}))",
    re.IGNORECASE,
)
RE_SO_HIEU = re.compile(r"(\d+/\d+/[A-ZĐ0-9\-]+)")


RE_DIEU_TRUOC = re.compile(
    r"(?:(điểm|Điểm)\s+([a-zđ])\s+)?"
    r"(?:(khoản|Khoản)\s+(\d+[a-zđ]?)\s+)?"
    r"(?:Điều|điều)\s+(\d+[a-zđ]?)(?=\s*(?:,|và|&))",
    re.IGNORECASE,
)


def _them_dan_chieu_truoc(
    text: str, pos: int, ten_vb: str | None,
    so_hieu: str | None, la_noi_bo: bool,
    kq: list[DanChieu], da_thay: set[tuple],
) -> None:
    """Scan nguoc truoc match chinh de tim 'Dieu N va' / 'Dieu N,' chia se context."""
    vung = text[max(0, pos - 150) : pos]
    for m in RE_DIEU_TRUOC.finditer(vung):
        diem = m.group(2)
        so_khoan = m.group(4)
        so_dieu = m.group(5)
        key = (so_dieu, so_khoan, diem, so_hieu, ten_vb or ("noi_bo" if la_noi_bo else "ngoai"))
        if key in da_thay:
            continue
        da_thay.add(key)
        kq.append(DanChieu(
            text_dan=m.group(0),
            so_hieu=so_hieu, ten_van_ban=ten_vb,
            so_dieu=so_dieu, so_khoan=so_khoan, diem=diem,
            la_noi_bo=la_noi_bo,
        ))


def trich_dan_chieu(text: str) -> list[DanChieu]:
    """Rut danh sach DanChieu tu mot doan text."""
    kq: list[DanChieu] = []
    da_thay: set[tuple] = set()

    for m in RE_NGOAI.finditer(text):
        diem = m.group(2)
        so_khoan = m.group(4)
        so_dieu = m.group(6)
        ten_vb = (m.group(7) or "").strip()
        so_hieu = m.group(8)
        if not so_hieu:
            m2 = RE_SO_HIEU.search(ten_vb)
            so_hieu = m2.group(1) if m2 else None
        key = (so_dieu, so_khoan, diem, so_hieu, ten_vb)
        if key in da_thay:
            continue
        da_thay.add(key)
        kq.append(DanChieu(
            text_dan=m.group(0),
            so_hieu=so_hieu, ten_van_ban=ten_vb,
            so_dieu=so_dieu, so_khoan=so_khoan, diem=diem,
            la_noi_bo=False,
        ))
        _them_dan_chieu_truoc(text, m.start(), ten_vb, so_hieu, False, kq, da_thay)

    for m in RE_NOI_BO.finditer(text):
        diem = m.group(2)
        so_khoan = m.group(4)
        so_dieu = m.group(6)
        key = (so_dieu, so_khoan, diem, None, "noi_bo")
        if key in da_thay:
            continue
        da_thay.add(key)
        kq.append(DanChieu(
            text_dan=m.group(0),
            so_hieu=None, ten_van_ban=m.group(7),
            so_dieu=so_dieu, so_khoan=so_khoan, diem=diem,
            la_noi_bo=True,
        ))
        _them_dan_chieu_truoc(text, m.start(), m.group(7), None, True, kq, da_thay)
    return kq


def ghi_dan_chieu_cho_van_ban(conn: Connection, van_ban_id: str) -> int:
    """Lap qua tung Khoan cua van ban, trich dan chieu, phan giai id, ghi vao dan_chieu."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, noi_dung FROM khoan WHERE van_ban_id=%s AND trang_thai <> 'bai_bo'",
            (van_ban_id,),
        )
        khoan_rows = cur.fetchall()

    so_ghi = 0
    with conn.cursor() as cur:
        # xoa dan chieu cu de idempotent
        cur.execute(
            "DELETE FROM dan_chieu WHERE nguon='luat' AND nguon_khoan_id IN "
            "(SELECT id FROM khoan WHERE van_ban_id=%s)",
            (van_ban_id,),
        )
        for khoan_id, noi_dung in khoan_rows:
            for dc in trich_dan_chieu(noi_dung or ""):
                vb_id, dieu_id, khoan_dich_id, ket_qua = _phan_giai(
                    cur, dc, van_ban_chua_id=van_ban_id,
                )
                cur.execute(
                    """INSERT INTO dan_chieu (
                         nguon, nguon_khoan_id, text_dan,
                         so_hieu, ten_van_ban, so_dieu, so_khoan, diem,
                         van_ban_id, dieu_id, khoan_id, ket_qua
                       ) VALUES ('luat',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (khoan_id, dc.text_dan, dc.so_hieu, dc.ten_van_ban,
                     dc.so_dieu, dc.so_khoan, dc.diem,
                     vb_id, dieu_id, khoan_dich_id, ket_qua),
                )
                so_ghi += 1
    return so_ghi


def _phan_giai(
    cur, dc: DanChieu, van_ban_chua_id: str,
) -> tuple[str | None, str | None, str | None, str]:
    """Phan giai DanChieu -> (van_ban_id, dieu_id, khoan_id, ket_qua)."""
    van_ban_id: str | None = None
    if dc.la_noi_bo:
        van_ban_id = van_ban_chua_id
    elif dc.so_hieu:
        cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (dc.so_hieu,))
        row = cur.fetchone()
        if row:
            van_ban_id = row[0]
    if van_ban_id is None:
        return None, None, None, "khong_xac_dinh"

    dieu_id: str | None = None
    khoan_id: str | None = None
    if dc.so_dieu:
        cur.execute(
            "SELECT id, trang_thai FROM dieu_luat "
            "WHERE van_ban_id=%s AND so_dieu=%s AND (hieu_luc_den IS NULL) "
            "ORDER BY hieu_luc_tu DESC NULLS LAST LIMIT 1",
            (van_ban_id, dc.so_dieu),
        )
        row = cur.fetchone()
        if row:
            dieu_id = row[0]
            if row[1] == "bai_bo":
                return van_ban_id, dieu_id, None, "bai_bo"
            if row[1] == "het_hieu_luc":
                return van_ban_id, dieu_id, None, "het_hieu_luc"
    if dc.so_khoan and dieu_id:
        cur.execute(
            "SELECT id, trang_thai FROM khoan "
            "WHERE dieu_id=%s AND so_khoan=%s AND "
            "((diem IS NULL AND %s::text IS NULL) OR diem=%s::text) "
            "AND (hieu_luc_den IS NULL) "
            "ORDER BY hieu_luc_tu DESC NULLS LAST LIMIT 1",
            (dieu_id, dc.so_khoan, dc.diem, dc.diem),
        )
        row = cur.fetchone()
        if row:
            khoan_id = row[0]
            if row[1] == "bai_bo":
                return van_ban_id, dieu_id, khoan_id, "bai_bo"
            if row[1] == "het_hieu_luc":
                return van_ban_id, dieu_id, khoan_id, "het_hieu_luc"
    if dc.so_dieu and dieu_id is None:
        return van_ban_id, None, None, "khong_ton_tai"
    return van_ban_id, dieu_id, khoan_id, "hop_le"

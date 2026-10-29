"""Lay ban hop nhat (muc luc theo thu tu) cua mot van ban me tai mot ngay."""
from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import Connection

from app.db.repo_hieu_luc import ban_hop_nhat, dieu_hieu_luc_tai


def muc_luc(
    conn: Connection, van_ban_id: str, ngay: date,
    chia_theo_chuong_khi_lon: bool = True, nguong_dieu: int = 300,
) -> list[dict[str, Any]]:
    """Tra ban hop nhat; neu > nguong_dieu thi gom theo Chuong."""
    rows = ban_hop_nhat(conn, van_ban_id, ngay)
    if not chia_theo_chuong_khi_lon or len(rows) <= nguong_dieu:
        return rows
    # Bo sung chuong_so cho moi hang tu dieu_luat
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, chuong_so, chuong_ten FROM dieu_luat WHERE van_ban_id=%s",
            (van_ban_id,),
        )
        chuong = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    for r in rows:
        c = chuong.get(r["dieu_id"], (None, None))
        r["chuong_so"] = c[0]
        r["chuong_ten"] = c[1]
    return rows


def noi_dung_dieu_full(conn: Connection, dieu_id: str) -> dict[str, Any] | None:
    """Lay 1 Dieu + Khoan de dua vao prompt tier2."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, van_ban_id, so_dieu, tieu_de, noi_dung, nguon_sua_doi_id
               FROM dieu_luat WHERE id=%s""", (dieu_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        d = {
            "id": row[0], "van_ban_id": row[1], "so_dieu": row[2],
            "tieu_de": row[3], "noi_dung": row[4], "nguon_sua_doi_id": row[5],
        }
        cur.execute(
            """SELECT id, so_khoan, diem, noi_dung
               FROM khoan WHERE dieu_id=%s AND trang_thai <> 'bai_bo'
               ORDER BY thu_tu""", (dieu_id,),
        )
        d["khoan"] = [
            {"id": r[0], "so_khoan": r[1], "diem": r[2], "noi_dung": r[3]}
            for r in cur.fetchall()
        ]
    return d

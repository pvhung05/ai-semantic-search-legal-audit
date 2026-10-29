"""Repository upsert van_ban/dieu_luat/khoan + truy van muc luc."""
from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import Connection

from app.models.schemas import Dieu, Khoan, VanBanMeta, VanBanParsed


def dieu_id(van_ban_id: str, so_dieu: str, hieu_luc_tu: date | None = None) -> str:
    base = f"{van_ban_id}:D{so_dieu}"
    return f"{base}@{hieu_luc_tu.isoformat()}" if hieu_luc_tu else base


def khoan_id(parent_dieu_id: str, so_khoan: str, diem: str | None) -> str:
    base = f"{parent_dieu_id}:K{so_khoan}"
    if diem:
        base = f"{base}:D{diem}"
    return base


def upsert_van_ban(conn: Connection, meta: VanBanMeta) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO van_ban (
              id, so_hieu, ten, loai, cap, co_quan_ban_hanh,
              ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc,
              la_van_ban_sua_doi, linh_vuc, tin_cay, nguon_file
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              so_hieu=EXCLUDED.so_hieu, ten=EXCLUDED.ten, loai=EXCLUDED.loai,
              cap=EXCLUDED.cap, co_quan_ban_hanh=EXCLUDED.co_quan_ban_hanh,
              ngay_ban_hanh=EXCLUDED.ngay_ban_hanh,
              ngay_hieu_luc=EXCLUDED.ngay_hieu_luc,
              ngay_het_hieu_luc=EXCLUDED.ngay_het_hieu_luc,
              la_van_ban_sua_doi=EXCLUDED.la_van_ban_sua_doi,
              linh_vuc=EXCLUDED.linh_vuc, tin_cay=EXCLUDED.tin_cay,
              nguon_file=EXCLUDED.nguon_file
            """,
            (
                meta.id, meta.so_hieu, meta.ten, meta.loai, meta.cap,
                meta.co_quan_ban_hanh, meta.ngay_ban_hanh, meta.ngay_hieu_luc,
                meta.ngay_het_hieu_luc, meta.la_van_ban_sua_doi,
                meta.linh_vuc, meta.tin_cay, meta.nguon_file,
            ),
        )
    return meta.id


def upsert_dieu(conn: Connection, van_ban_id: str, dieu: Dieu, hieu_luc_tu: date | None = None) -> str:
    did = dieu_id(van_ban_id, dieu.so_dieu, hieu_luc_tu)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dieu_luat (
              id, van_ban_id, so_dieu, so_dieu_num,
              chuong_so, chuong_ten, muc_so, muc_ten,
              tieu_de, noi_dung, tom_tat, thu_tu,
              trang_thai, hieu_luc_tu, hieu_luc_den
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              so_dieu=EXCLUDED.so_dieu, so_dieu_num=EXCLUDED.so_dieu_num,
              chuong_so=EXCLUDED.chuong_so, chuong_ten=EXCLUDED.chuong_ten,
              muc_so=EXCLUDED.muc_so, muc_ten=EXCLUDED.muc_ten,
              tieu_de=EXCLUDED.tieu_de, noi_dung=EXCLUDED.noi_dung,
              tom_tat=EXCLUDED.tom_tat, thu_tu=EXCLUDED.thu_tu
            """,
            (
                did, van_ban_id, dieu.so_dieu, dieu.so_dieu_num,
                dieu.chuong_so, dieu.chuong_ten, dieu.muc_so, dieu.muc_ten,
                dieu.tieu_de, dieu.noi_dung, dieu.tom_tat, dieu.thu_tu,
                "con_hieu_luc", hieu_luc_tu, None,
            ),
        )
    return did


def upsert_khoan(
    conn: Connection,
    parent_dieu_id: str,
    van_ban_id: str,
    khoan: Khoan,
    parent_khoan_id: str | None = None,
    hieu_luc_tu: date | None = None,
) -> str:
    kid = khoan_id(parent_dieu_id, khoan.so_khoan, khoan.diem)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO khoan (
              id, dieu_id, van_ban_id, so_khoan, diem, parent_id,
              noi_dung, thu_tu, trang_thai, hieu_luc_tu, hieu_luc_den
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              so_khoan=EXCLUDED.so_khoan, diem=EXCLUDED.diem,
              parent_id=EXCLUDED.parent_id, noi_dung=EXCLUDED.noi_dung,
              thu_tu=EXCLUDED.thu_tu
            """,
            (
                kid, parent_dieu_id, van_ban_id, khoan.so_khoan, khoan.diem,
                parent_khoan_id, khoan.noi_dung, khoan.thu_tu,
                "con_hieu_luc", hieu_luc_tu, None,
            ),
        )
    return kid


def luu_van_ban_day_du(
    conn: Connection, parsed: VanBanParsed, hieu_luc_tu: date | None = None
) -> dict[str, int]:
    """Luu toan bo van ban + Dieu + Khoan. Idempotent."""
    van_ban_id = upsert_van_ban(conn, parsed.meta)
    so_dieu = 0
    so_khoan = 0
    for d in parsed.dieu:
        did = upsert_dieu(conn, van_ban_id, d, hieu_luc_tu=hieu_luc_tu)
        so_dieu += 1
        # chen Khoan truoc, Diem sau (co parent_id la Khoan)
        khoan_ids_theo_so: dict[str, str] = {}
        for k in d.khoan:
            if k.diem is None:
                kid = upsert_khoan(conn, did, van_ban_id, k, hieu_luc_tu=hieu_luc_tu)
                khoan_ids_theo_so[k.so_khoan] = kid
                so_khoan += 1
        for k in d.khoan:
            if k.diem is not None:
                parent_kid = khoan_ids_theo_so.get(k.parent_so_khoan or k.so_khoan)
                upsert_khoan(
                    conn, did, van_ban_id, k,
                    parent_khoan_id=parent_kid, hieu_luc_tu=hieu_luc_tu,
                )
                so_khoan += 1
    return {"so_dieu": so_dieu, "so_khoan": so_khoan}


def get_muc_luc(conn: Connection, van_ban_id: str, ngay: date) -> list[dict[str, Any]]:
    """Danh sach Dieu con hieu luc tai ngay, dung ban_hop_nhat()."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dieu_id, so_dieu, tieu_de, tom_tat, thu_tu FROM ban_hop_nhat(%s, %s) ORDER BY thu_tu",
            (van_ban_id, ngay),
        )
        return [
            {
                "dieu_id": r[0], "so_dieu": r[1], "tieu_de": r[2],
                "tom_tat": r[3], "thu_tu": r[4],
            }
            for r in cur.fetchall()
        ]


def get_dieu_full(conn: Connection, dieu_id_param: str) -> dict[str, Any] | None:
    """Lay Dieu + cac Khoan + Diem."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, van_ban_id, so_dieu, tieu_de, noi_dung, tom_tat, thu_tu, trang_thai
               FROM dieu_luat WHERE id=%s""",
            (dieu_id_param,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        dieu = {
            "id": row[0], "van_ban_id": row[1], "so_dieu": row[2],
            "tieu_de": row[3], "noi_dung": row[4], "tom_tat": row[5],
            "thu_tu": row[6], "trang_thai": row[7],
        }
        cur.execute(
            """SELECT id, so_khoan, diem, parent_id, noi_dung, thu_tu, trang_thai
               FROM khoan WHERE dieu_id=%s ORDER BY thu_tu""",
            (dieu_id_param,),
        )
        dieu["khoan"] = [
            {
                "id": r[0], "so_khoan": r[1], "diem": r[2], "parent_id": r[3],
                "noi_dung": r[4], "thu_tu": r[5], "trang_thai": r[6],
            }
            for r in cur.fetchall()
        ]
    return dieu

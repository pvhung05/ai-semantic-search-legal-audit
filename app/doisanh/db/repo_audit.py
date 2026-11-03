"""Repository phien doi chieu + van ban me + anh xa + ket qua + cache."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from psycopg import Connection


def sinh_id_phien() -> str:
    return "PH-" + uuid.uuid4().hex[:8]


def tao_phien(
    conn: Connection, tai_lieu_id: str, ngay_tra: date,
    che_do: str = "cay", tu_dong_duyet: bool = False,
) -> str:
    pid = sinh_id_phien()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO phien_doi_chieu (id, tai_lieu_id, ngay_tra, che_do, tu_dong_duyet, buoc)
               VALUES (%s,%s,%s,%s,%s,'tao')""",
            (pid, tai_lieu_id, ngay_tra, che_do, tu_dong_duyet),
        )
    return pid


def cap_nhat_buoc(conn: Connection, phien_id: str, buoc: str, loi: str | None = None,
                  thong_ke: dict | None = None) -> None:
    import json
    with conn.cursor() as cur:
        if thong_ke is None:
            cur.execute(
                "UPDATE phien_doi_chieu SET buoc=%s, loi=%s, updated_at=now() WHERE id=%s",
                (buoc, loi, phien_id),
            )
        else:
            cur.execute(
                "UPDATE phien_doi_chieu SET buoc=%s, loi=%s, thong_ke=%s, updated_at=now() WHERE id=%s",
                (buoc, loi, json.dumps(thong_ke), phien_id),
            )


def lay_phien(conn: Connection, phien_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, tai_lieu_id, ngay_tra, che_do, tu_dong_duyet, buoc, loi, thong_ke
               FROM phien_doi_chieu WHERE id=%s""",
            (phien_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c.name for c in cur.description]
        return dict(zip(cols, row))


def luu_van_ban_me(
    conn: Connection, phien_id: str, van_ban_id: str,
    nguon: str, buoc_sau: int = 0, duyet: str = "de_xuat",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO phien_van_ban_me (phien_id, van_ban_id, nguon, buoc_sau, duyet)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (phien_id, van_ban_id) DO UPDATE SET
                 nguon=EXCLUDED.nguon, buoc_sau=EXCLUDED.buoc_sau""",
            (phien_id, van_ban_id, nguon, buoc_sau, duyet),
        )


def danh_sach_van_ban_me(conn: Connection, phien_id: str, duyet: str | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        if duyet:
            cur.execute(
                "SELECT van_ban_id, nguon, buoc_sau, duyet FROM phien_van_ban_me "
                "WHERE phien_id=%s AND duyet=%s", (phien_id, duyet),
            )
        else:
            cur.execute(
                "SELECT van_ban_id, nguon, buoc_sau, duyet FROM phien_van_ban_me WHERE phien_id=%s",
                (phien_id,),
            )
        return [{"van_ban_id": r[0], "nguon": r[1], "buoc_sau": r[2], "duyet": r[3]}
                for r in cur.fetchall()]


def duyet_van_ban_me(conn: Connection, phien_id: str, van_ban_ids: list[str], duyet: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE phien_van_ban_me SET duyet=%s WHERE phien_id=%s AND van_ban_id = ANY(%s)",
            (duyet, phien_id, van_ban_ids),
        )


def luu_anh_xa(
    conn: Connection, phien_id: str, don_vi_id: str,
    dieu_me_id: str | None, loai: str, tin_cay: float,
    nguon: str, duyet: str = "de_xuat", hash_cap: str | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO anh_xa_dieu (phien_id, don_vi_id, dieu_me_id, loai,
                                          tin_cay, nguon, duyet, hash_cap)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (phien_id, don_vi_id, dieu_me_id, loai, tin_cay, nguon, duyet, hash_cap),
        )
        return cur.fetchone()[0]


def danh_sach_anh_xa(conn: Connection, phien_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, don_vi_id, dieu_me_id, loai, tin_cay, nguon, duyet, hash_cap
               FROM anh_xa_dieu WHERE phien_id=%s ORDER BY id""",
            (phien_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def luu_ket_qua(
    conn: Connection, phien_id: str, don_vi_id: str, tang: int,
    loai_loi: str, muc_do: str, tin_cay: float,
    anh_xa_id: int | None = None,
    can_cu_van_ban_id: str | None = None,
    can_cu_dieu_id: str | None = None,
    can_cu_khoan_id: str | None = None,
    can_cu_trich_dan: str | None = None,
    doan_du_thao: str | None = None,
    giai_thich: str | None = None,
    de_xuat_sua: str | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ket_qua_doi_chieu (
                 phien_id, don_vi_id, tang, loai_loi, muc_do, tin_cay,
                 anh_xa_id, can_cu_van_ban_id, can_cu_dieu_id, can_cu_khoan_id,
                 can_cu_trich_dan, doan_du_thao, giai_thich, de_xuat_sua
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (phien_id, don_vi_id, tang, loai_loi, muc_do, tin_cay, anh_xa_id,
             can_cu_van_ban_id, can_cu_dieu_id, can_cu_khoan_id,
             can_cu_trich_dan, doan_du_thao, giai_thich, de_xuat_sua),
        )
        return cur.fetchone()[0]


def danh_sach_ket_qua(conn: Connection, phien_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM ket_qua_doi_chieu WHERE phien_id=%s
               ORDER BY tang, don_vi_id""",
            (phien_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def cache_tier2_get(conn: Connection, hash_cap: str, cau_hinh_hash: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ket_qua FROM tier2_cache WHERE hash_cap=%s AND cau_hinh_hash=%s",
            (hash_cap, cau_hinh_hash),
        )
        row = cur.fetchone()
        return row[0] if row else None


def cache_tier2_set(conn: Connection, hash_cap: str, cau_hinh_hash: str, ket_qua: dict) -> None:
    import json
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO tier2_cache (hash_cap, cau_hinh_hash, ket_qua) VALUES (%s,%s,%s)
               ON CONFLICT (hash_cap, cau_hinh_hash) DO UPDATE SET ket_qua=EXCLUDED.ket_qua""",
            (hash_cap, cau_hinh_hash, json.dumps(ket_qua)),
        )

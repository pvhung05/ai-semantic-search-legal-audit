"""Rut quan he van ban khi nap: can_cu (tu phan Can cu), quy_dinh_chi_tiet (tu ten)."""
from __future__ import annotations

import re
from typing import Iterable

from psycopg import Connection

RE_SO_HIEU = re.compile(r"(\d+/\d+/[A-ZĐ0-9\-]+)")
RE_QUY_DINH_CHI_TIET = re.compile(
    r"(?:quy định chi tiết|hướng dẫn thi hành)\s+(?:một số điều của\s+)?",
    re.IGNORECASE,
)


def _tim_vb_id_tu_so_hieu(cur, so_hieu: str) -> str | None:
    cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (so_hieu,))
    row = cur.fetchone()
    return row[0] if row else None


def ghi_can_cu(conn: Connection, van_ban_id: str, can_cu_tho: Iterable[str]) -> int:
    """Moi dong can cu co 'so hieu' -> them canh can_cu toi van ban do neu da nap."""
    so = 0
    with conn.cursor() as cur:
        for dong in can_cu_tho:
            for sh in set(RE_SO_HIEU.findall(dong)):
                dich_id = _tim_vb_id_tu_so_hieu(cur, sh)
                if not dich_id or dich_id == van_ban_id:
                    continue
                cur.execute(
                    """INSERT INTO quan_he_van_ban (nguon_id, dich_id, loai, nguon_lenh, da_ap_dung, tin_cay)
                       VALUES (%s,%s,'can_cu','can_cu',true,'xac_nhan')
                       ON CONFLICT DO NOTHING""",
                    (van_ban_id, dich_id),
                )
                so += cur.rowcount or 0
    return so


def ghi_quy_dinh_chi_tiet(conn: Connection, van_ban_id: str, ten_van_ban: str) -> int:
    """Neu ten chua 'quy dinh chi tiet'/'huong dan thi hanh' + so hieu -> them canh."""
    so = 0
    if not RE_QUY_DINH_CHI_TIET.search(ten_van_ban or ""):
        return 0
    with conn.cursor() as cur:
        for sh in set(RE_SO_HIEU.findall(ten_van_ban)):
            dich_id = _tim_vb_id_tu_so_hieu(cur, sh)
            if not dich_id or dich_id == van_ban_id:
                continue
            cur.execute(
                """INSERT INTO quan_he_van_ban (nguon_id, dich_id, loai, nguon_lenh, da_ap_dung, tin_cay)
                   VALUES (%s,%s,'quy_dinh_chi_tiet','ten',true,'xac_nhan')
                   ON CONFLICT DO NOTHING""",
                (van_ban_id, dich_id),
            )
            so += cur.rowcount or 0
    return so

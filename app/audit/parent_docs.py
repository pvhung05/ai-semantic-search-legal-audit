"""Xac dinh van ban me cho mot tai lieu du thao.

Thu tu nguon:
  can_cu -> quan_he -> dan_chieu -> chu_de -> truy_hoi (chi khi ENABLE_FALLBACK)

Luat nen:
  co che tai -> Luat XLVPHC;
  la VBQPPL -> Luat Ban hanh VBQPPL (chi tier1 the thuc).

loai_cay: ro | mo | khong
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from psycopg import Connection

from app.config import settings

RE_SO_HIEU = re.compile(r"(\d+/\d+/[A-ZĐ\-]+)")


@dataclass
class VanBanMeDeXuat:
    van_ban_id: str
    nguon: str  # can_cu|quan_he|dan_chieu|chu_de|truy_hoi
    buoc_sau: int = 0
    diem_so: float = 0.0


@dataclass
class KetQuaParentDocs:
    de_xuat: list[VanBanMeDeXuat] = field(default_factory=list)
    loai_cay: str = "khong"  # ro|mo|khong


def _tim_vb_tu_can_cu(cur, can_cu_tho: list[str]) -> list[VanBanMeDeXuat]:
    kq: list[VanBanMeDeXuat] = []
    seen: set[str] = set()
    for dong in can_cu_tho:
        for sh in RE_SO_HIEU.findall(dong):
            cur.execute("SELECT id FROM van_ban WHERE so_hieu=%s", (sh,))
            row = cur.fetchone()
            if row and row[0] not in seen:
                seen.add(row[0])
                kq.append(VanBanMeDeXuat(van_ban_id=row[0], nguon="can_cu", buoc_sau=0, diem_so=1.0))
    return kq


def _tim_vb_qua_do_thi(cur, van_ban_ids: list[str]) -> list[VanBanMeDeXuat]:
    if not van_ban_ids:
        return []
    cur.execute(
        "SELECT van_ban_id, buoc_sau FROM van_ban_me_qua_do_thi(%s) WHERE van_ban_id <> ALL(%s)",
        (van_ban_ids, van_ban_ids),
    )
    return [
        VanBanMeDeXuat(van_ban_id=r[0], nguon="quan_he", buoc_sau=r[1],
                       diem_so=max(0.1, 1.0 - 0.3 * r[1]))
        for r in cur.fetchall()
    ]


def _tim_vb_qua_dan_chieu(cur, tai_lieu_id: str, nguong: int = 2) -> list[VanBanMeDeXuat]:
    cur.execute(
        """SELECT dc.van_ban_id, COUNT(*) AS so_lan FROM dan_chieu dc
           JOIN tai_lieu_don_vi dv ON dv.id = dc.nguon_don_vi_id
           WHERE dv.tai_lieu_id=%s AND dc.nguon='tai_lieu' AND dc.van_ban_id IS NOT NULL
           GROUP BY dc.van_ban_id HAVING COUNT(*) >= %s""",
        (tai_lieu_id, nguong),
    )
    return [VanBanMeDeXuat(van_ban_id=r[0], nguon="dan_chieu", buoc_sau=0,
                           diem_so=min(0.9, 0.3 + 0.1 * r[1]))
            for r in cur.fetchall()]


def _tim_vb_qua_chu_de(cur, loai_tai_lieu: str, linh_vuc: list[str]) -> list[VanBanMeDeXuat]:
    if not linh_vuc:
        return []
    cur.execute(
        "SELECT DISTINCT van_ban_id FROM chu_de_van_ban_me "
        "WHERE loai_tai_lieu=%s AND linh_vuc = ANY(%s)",
        (loai_tai_lieu, linh_vuc),
    )
    return [VanBanMeDeXuat(van_ban_id=r[0], nguon="chu_de", buoc_sau=0, diem_so=0.3)
            for r in cur.fetchall()]


def _tim_vb_qua_truy_hoi(
    conn: Connection, tai_lieu_id: str, linh_vuc: list[str],
) -> list[VanBanMeDeXuat]:
    try:
        from app.retrieval.hybrid import tim_hybrid_tu_text
    except ImportError:
        return []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT noi_dung FROM tai_lieu_don_vi WHERE tai_lieu_id=%s "
            "ORDER BY thu_tu LIMIT 20",
            (tai_lieu_id,),
        )
        texts = [r[0] for r in cur.fetchall()]
    gop = "\n".join(texts)[:4000]
    if not gop:
        return []
    try:
        rows = tim_hybrid_tu_text(conn, gop, linh_vuc=linh_vuc or None, top_k=15,
                                  nguong=settings.AUDIT_NGUONG_FALLBACK)
    except Exception:
        return []
    seen: set[str] = set()
    out: list[VanBanMeDeXuat] = []
    for r in rows:
        vb = r.get("van_ban_id")
        if not vb or vb in seen:
            continue
        seen.add(vb)
        out.append(VanBanMeDeXuat(van_ban_id=vb, nguon="truy_hoi", buoc_sau=0,
                                  diem_so=min(0.6, r["diem_rrf"])))
    return out


def de_xuat_van_ban_me(
    conn: Connection, tai_lieu_id: str, loai_tai_lieu: str,
    linh_vuc: list[str], can_cu_tho: list[str],
) -> KetQuaParentDocs:
    kq = KetQuaParentDocs()
    all_dx: dict[str, VanBanMeDeXuat] = {}

    with conn.cursor() as cur:
        # 1. can cu
        tu_can_cu = _tim_vb_tu_can_cu(cur, can_cu_tho)
        for dx in tu_can_cu:
            all_dx[dx.van_ban_id] = dx

        # 2. quan he
        tu_qh = _tim_vb_qua_do_thi(cur, list(all_dx.keys()))
        for dx in tu_qh:
            if dx.van_ban_id not in all_dx:
                all_dx[dx.van_ban_id] = dx

        # 3. dan chieu
        tu_dc = _tim_vb_qua_dan_chieu(cur, tai_lieu_id)
        for dx in tu_dc:
            if dx.van_ban_id not in all_dx:
                all_dx[dx.van_ban_id] = dx

        # 4. chu de
        tu_cd = _tim_vb_qua_chu_de(cur, loai_tai_lieu, linh_vuc)
        for dx in tu_cd:
            if dx.van_ban_id not in all_dx:
                all_dx[dx.van_ban_id] = dx

        # 5. truy_hoi (GD E, chi khi ENABLE_FALLBACK)
        if settings.ENABLE_FALLBACK:
            tu_th = _tim_vb_qua_truy_hoi(conn, tai_lieu_id, linh_vuc)
            for dx in tu_th:
                if dx.van_ban_id not in all_dx:
                    all_dx[dx.van_ban_id] = dx

    kq.de_xuat = sorted(all_dx.values(), key=lambda d: (-d.diem_so, d.buoc_sau))

    co_can_cu_hay_qh = any(dx.nguon in {"can_cu", "quan_he"} for dx in kq.de_xuat)
    co_dc_hay_cd = any(dx.nguon in {"dan_chieu", "chu_de"} for dx in kq.de_xuat)
    if co_can_cu_hay_qh:
        kq.loai_cay = "ro"
    elif co_dc_hay_cd:
        kq.loai_cay = "mo"
    else:
        kq.loai_cay = "khong"

    # Gioi han so luong
    kq.de_xuat = kq.de_xuat[: settings.AUDIT_MAX_DIEU_ME * 2]
    return kq

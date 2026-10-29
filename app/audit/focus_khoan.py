"""Buoc 'focus Khoan': voi moi Khoan/doan cua du thao, chon top-k Khoan me co lien quan
nhat bang hybrid retrieval (embedding + BM25) trong pham vi cac Dieu me da duoc anh xa.

Thu tu:
1. Lay ra cac khoan.id cua tat ca Dieu me duoc mapping (sau khi duyet).
2. Voi moi Khoan du thao, embed noi_dung, hybrid search gioi han trong tap khoan.id tren.
3. Loc theo nguong_rrf, cap_max neu can.
4. Them 'ngu canh': Khoan truoc, Khoan sau cung Dieu de LLM dung.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from psycopg import Connection

from app.audit.segment import DonViSegment
from app.config import settings
from app.models.embedder import embed

logger = logging.getLogger(__name__)


@dataclass
class KhoanUngVien:
    """Mot Khoan me duoc chon lam ung vien cho mot Khoan du thao."""
    khoan_id: str
    dieu_id: str
    van_ban_id: str
    so_dieu: str
    so_khoan: str
    diem: str | None
    noi_dung: str
    tieu_de_dieu: str | None
    da_sua: bool = False
    diem_rrf: float = 0.0
    ngu_canh_truoc: str | None = None
    ngu_canh_sau: str | None = None


@dataclass
class FocusKhoan:
    don_vi_id: str  # id cua Khoan/doan du thao
    ung_vien: list[KhoanUngVien] = field(default_factory=list)


def _lay_khoan_ids_tu_dieu_me(conn: Connection, dieu_me_ids: list[str]) -> list[str]:
    """Lay tat ca khoan.id (bao gom Diem) thuoc cac Dieu me da mapping, con hieu luc."""
    if not dieu_me_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM khoan
               WHERE dieu_id = ANY(%s) AND trang_thai <> 'bai_bo'
                     AND (hieu_luc_den IS NULL)
               ORDER BY dieu_id, thu_tu""",
            (dieu_me_ids,),
        )
        return [r[0] for r in cur.fetchall()]


def _lay_khoan_ids_tu_van_ban_me(conn: Connection, van_ban_me_ids: list[str]) -> list[str]:
    """Lay tat ca khoan.id thuoc cac VB me, con hieu luc."""
    if not van_ban_me_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM khoan
               WHERE van_ban_id = ANY(%s) AND trang_thai <> 'bai_bo'
                     AND (hieu_luc_den IS NULL)""",
            (van_ban_me_ids,),
        )
        return [r[0] for r in cur.fetchall()]


def _hybrid_khoan(
    conn: Connection, text: str, khoan_id_pool: list[str],
    top_k: int, ngay: date,
) -> list[tuple[str, float]]:
    """Hybrid search chi gioi han trong tap khoan.id da cho; tra [(chunk_id, diem_rrf)]."""
    if not khoan_id_pool:
        return []
    emb = embed(text[:2000])
    emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH loc AS (
              SELECT id, embedding, tsv_goc FROM chunk
              WHERE khoan_id = ANY(%s) AND embedding IS NOT NULL
                AND (hieu_luc_tu IS NULL OR hieu_luc_tu <= %s)
                AND (hieu_luc_den IS NULL OR hieu_luc_den >= %s)
            ),
            vec AS (SELECT id, row_number() OVER (ORDER BY embedding <=> %s::vector) r
                    FROM loc ORDER BY embedding <=> %s::vector LIMIT %s),
            bm  AS (SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv_goc, q) DESC) r
                    FROM loc, plainto_tsquery('simple', %s) q
                    WHERE tsv_goc @@ q LIMIT %s)
            SELECT COALESCE(v.id, b.id),
                   (COALESCE(1.0/(60+v.r),0) + COALESCE(1.0/(60+b.r),0))::real
            FROM vec v FULL OUTER JOIN bm b ON v.id = b.id
            ORDER BY 2 DESC LIMIT %s
            """,
            (khoan_id_pool, ngay, ngay, emb_str, emb_str, top_k * 3,
             text[:500], top_k * 3, top_k),
        )
        return [(r[0], float(r[1])) for r in cur.fetchall()]


def _nap_chi_tiet_khoan(
    conn: Connection, khoan_ids: list[str], diem_map: dict[str, float],
) -> list[KhoanUngVien]:
    if not khoan_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """SELECT k.id, k.dieu_id, k.van_ban_id, d.so_dieu, k.so_khoan, k.diem,
                      k.noi_dung, d.tieu_de, d.nguon_sua_doi_id, k.thu_tu
               FROM khoan k JOIN dieu_luat d ON d.id = k.dieu_id
               WHERE k.id = ANY(%s)""",
            (khoan_ids,),
        )
        ket = []
        for r in cur.fetchall():
            ket.append(KhoanUngVien(
                khoan_id=r[0], dieu_id=r[1], van_ban_id=r[2],
                so_dieu=r[3], so_khoan=r[4], diem=r[5], noi_dung=r[6] or "",
                tieu_de_dieu=r[7], da_sua=r[8] is not None,
                diem_rrf=diem_map.get(r[0], 0.0),
            ))
    return ket


def _bo_sung_ngu_canh(conn: Connection, ung_vien: list[KhoanUngVien]) -> None:
    """Them Khoan truoc va Khoan sau de LLM co ngu canh."""
    if not ung_vien:
        return
    dieu_ids = list({u.dieu_id for u in ung_vien})
    with conn.cursor() as cur:
        cur.execute(
            """SELECT dieu_id, thu_tu, noi_dung, so_khoan, diem
               FROM khoan WHERE dieu_id = ANY(%s) AND trang_thai <> 'bai_bo'
               ORDER BY dieu_id, thu_tu""",
            (dieu_ids,),
        )
        theo_dieu: dict[str, list[tuple]] = {}
        for did, tt, nd, sk, dm in cur.fetchall():
            theo_dieu.setdefault(did, []).append((tt, nd, sk, dm))
    for uv in ung_vien:
        ds = theo_dieu.get(uv.dieu_id, [])
        idx = next((i for i, (_, _, sk, dm) in enumerate(ds)
                    if sk == uv.so_khoan and dm == uv.diem), -1)
        if idx > 0:
            _, nd, sk, dm = ds[idx - 1]
            uv.ngu_canh_truoc = f"[Khoan truoc {sk}{'' if not dm else '/'+dm}] " + nd[:300]
        if 0 <= idx < len(ds) - 1:
            _, nd, sk, dm = ds[idx + 1]
            uv.ngu_canh_sau = f"[Khoan sau {sk}{'' if not dm else '/'+dm}] " + nd[:300]


def focus_khoan(
    conn: Connection, don_vi_list: list[DonViSegment],
    dieu_me_ids: list[str] | None = None,
    van_ban_me_ids: list[str] | None = None,
    ngay: date = date.today(), top_k: int = 5, nguong_rrf: float = 0.0,
    them_ngu_canh: bool = True,
) -> list[FocusKhoan]:
    """Voi moi Khoan/Diem/doan/cum cua du thao -> top-k Khoan me co lien quan.

    - dieu_me_ids: pham vi hep (anh xa chat).
    - van_ban_me_ids: pham vi rong (ca VB me), dung khi khong co anh xa Dieu.
    """
    if dieu_me_ids:
        khoan_id_pool = _lay_khoan_ids_tu_dieu_me(conn, dieu_me_ids)
    else:
        khoan_id_pool = _lay_khoan_ids_tu_van_ban_me(conn, van_ban_me_ids or [])
    if not khoan_id_pool:
        logger.warning("Khong co khoan nao trong pham vi Dieu me da chon")
        return []

    ket_qua: list[FocusKhoan] = []
    for dv in don_vi_list:
        if dv.cap not in {"khoan", "diem", "doan"}:
            continue
        text_embed = (
            (dv.tieu_de + ". " + dv.noi_dung) if dv.tieu_de else (dv.noi_dung or "")
        )
        try:
            rows = _hybrid_khoan(conn, text_embed, khoan_id_pool, top_k, ngay)
        except Exception as exc:
            logger.warning("hybrid loi don_vi=%s: %s", dv.id, exc)
            rows = []
        rows = [(kid, s) for kid, s in rows if s >= nguong_rrf]
        if not rows:
            ket_qua.append(FocusKhoan(don_vi_id=dv.id, ung_vien=[]))
            continue
        diem_map = dict(rows)
        ung_vien = _nap_chi_tiet_khoan(conn, [kid for kid, _ in rows], diem_map)
        ung_vien.sort(key=lambda u: -u.diem_rrf)
        if them_ngu_canh:
            _bo_sung_ngu_canh(conn, ung_vien)
        ket_qua.append(FocusKhoan(don_vi_id=dv.id, ung_vien=ung_vien))
    return ket_qua

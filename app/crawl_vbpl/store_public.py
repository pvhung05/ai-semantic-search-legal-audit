"""Nap CAY noi dung (tu doc_api.fetch_cay_noidung) vao schema `public` dang node.

Mot node = mot dong `public.node` (Chuong/Muc/Dieu/Khoan/Diem), khoa = UUID vbpl.
Node la -> sinh `public.chunk` (text da lam sach, chua embedding - de GD embedding sau).
`public.van_ban` lay lai metadata tu `meta.documents` (nguon metadata duy nhat).

save_cay idempotent: xoa sach node cu cua van_ban roi nap lai (chunk CASCADE theo node).
"""
from __future__ import annotations

import logging
import re
from datetime import date

import psycopg

from .parser import html_doc_to_text

log = logging.getLogger(__name__)

# level (API) -> cap_node (enum public)
_LEVEL_CAP = {
    "Chapter": "chuong",
    "Section": "muc",
    "Article": "dieu",
    "Clause":  "khoan",
    "Point":   "diem",
}
_CAP_PREFIX = {"chuong": "C", "muc": "M", "dieu": "D", "khoan": "K", "diem": "d"}

# trang thai hop le cua public.trangthai_node
_NODE_TT = {
    "chua_hieu_luc", "con_hieu_luc", "het_hieu_luc_mot_phan",
    "het_hieu_luc", "bai_bo", "khong_xac_dinh",
}

_RE_STT = {
    "chuong": re.compile(r"Chương\s+([IVXLCDM0-9]+[A-Za-zđ]?)", re.I),
    "muc":    re.compile(r"Mục\s+([0-9IVXLCDM]+[A-Za-zđ]?)", re.I),
    "dieu":   re.compile(r"Điều\s+(\d+[a-zđ]?)", re.I),
    "khoan":  re.compile(r"Khoản\s+(\d+[a-zđ]?)", re.I),
    "diem":   re.compile(r"Điểm\s+([a-zđ0-9]+)", re.I),
}
_RE_STT_FALLBACK = {
    "khoan": re.compile(r"^\s*(\d+[a-zđ]?)\s*[\.\)]"),
    "diem":  re.compile(r"^\s*([a-zđ])\s*\)"),
}


def _map_trang_thai(meta_val: str | None) -> str:
    v = (meta_val or "").strip().lower()
    return v if v in _NODE_TT else "khong_xac_dinh"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _so_thu_tu(cap: str, node: dict) -> str | None:
    content = node.get("content") or {}
    title = (content.get("title") or node.get("title") or "").split("\n")[0]
    rx = _RE_STT.get(cap)
    m = rx.search(title) if rx else None
    if not m and cap in _RE_STT_FALLBACK:
        m = _RE_STT_FALLBACK[cap].search(title)
    return m.group(1) if m else None


def _flatten(tree: list[dict], van_ban_id: str) -> list[dict]:
    """Duyet pre-order (cha truoc con) de thoa FK self-reference parent_id."""
    rows: list[dict] = []

    def walk(nodes: list[dict], parent_id: str | None, path: str) -> None:
        for n in nodes:
            nid = n.get("id") or n.get("key")
            level = n.get("level")
            cap = _LEVEL_CAP.get(level or "")
            if not nid:
                log.warning("node khong co id (level=%s), bo qua", level)
                continue
            if cap is None:
                log.warning("level '%s' chua map (node %s), bo qua ca nhanh", level, nid)
                continue
            stt = _so_thu_tu(cap, n)
            seg = _CAP_PREFIX[cap] + (stt or "?")
            duong_dan = f"{path}>{seg}" if path else seg
            content = n.get("content") or {}
            rows.append({
                "id": nid,
                "van_ban_id": van_ban_id,
                "parent_id": parent_id,
                "cap": cap,
                "ptype": n.get("ptype"),
                "so_thu_tu": stt,
                "tieu_de": (n.get("title") or "").strip() or None,
                "noi_dung": content.get("content"),
                "order_index": n.get("orderIndex"),
                "is_leaf": bool(n.get("isLeaf")),
                "duong_dan": duong_dan,
                "hieu_luc_tu": _parse_date(n.get("effFrom")),
                "hieu_luc_den": _parse_date(n.get("effTo")),
            })
            walk(n.get("children") or [], nid, duong_dan)

    walk(tree, None, "")
    return rows


def _upsert_van_ban(cur: psycopg.Cursor, van_ban_id: str) -> None:
    cur.execute(
        """SELECT d.so_hieu, d.tieu_de, lv.ten, d.ngay_banhanh, d.ngay_hieuluc,
                  d.ngay_hethieuluc, d.trangthai::text
           FROM meta.documents d
           LEFT JOIN meta.loai_vanban lv ON lv.id = d.loai_vanban_id
           WHERE d.id = %s""",
        (van_ban_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"van ban {van_ban_id} chua co trong meta.documents (FK)")
    so_hieu, ten, loai, nbh, nhl, nhhl, tt = row
    cur.execute(
        """INSERT INTO public.van_ban
             (id, so_hieu, ten, loai, ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc, trang_thai)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO UPDATE SET
             so_hieu=EXCLUDED.so_hieu, ten=EXCLUDED.ten, loai=EXCLUDED.loai,
             ngay_ban_hanh=EXCLUDED.ngay_ban_hanh, ngay_hieu_luc=EXCLUDED.ngay_hieu_luc,
             ngay_het_hieu_luc=EXCLUDED.ngay_het_hieu_luc, trang_thai=EXCLUDED.trang_thai""",
        (van_ban_id, so_hieu, ten, loai, nbh, nhl, nhhl, _map_trang_thai(tt)),
    )


def save_cay(conn: psycopg.Connection, van_ban_id: str, tree: list[dict]) -> dict[str, int]:
    """Nap cay vao public.node + public.chunk. Tra ve so luong da ghi."""
    van_ban_id = str(van_ban_id).strip()
    rows = _flatten(tree, van_ban_id)

    with conn.cursor() as cur:
        _upsert_van_ban(cur, van_ban_id)
        # idempotent: xoa node cu (chunk CASCADE theo node)
        cur.execute("DELETE FROM public.node WHERE van_ban_id = %s", (van_ban_id,))

        cur.executemany(
            """INSERT INTO public.node
                 (id, van_ban_id, parent_id, cap, ptype, so_thu_tu, tieu_de, noi_dung,
                  order_index, is_leaf, duong_dan, hieu_luc_tu, hieu_luc_den)
               VALUES (%(id)s, %(van_ban_id)s, %(parent_id)s, %(cap)s, %(ptype)s, %(so_thu_tu)s,
                       %(tieu_de)s, %(noi_dung)s, %(order_index)s, %(is_leaf)s, %(duong_dan)s,
                       %(hieu_luc_tu)s, %(hieu_luc_den)s)""",
            rows,
        )

        chunks = []
        for r in rows:
            if not r["is_leaf"] or not r["noi_dung"]:
                continue
            text = html_doc_to_text(r["noi_dung"]).strip()
            if not text:
                continue
            chunks.append((r["id"], van_ban_id, text, r["hieu_luc_tu"], r["hieu_luc_den"]))
        if chunks:
            cur.executemany(
                """INSERT INTO public.chunk
                     (node_id, van_ban_id, text_goc, hieu_luc_tu, hieu_luc_den)
                   VALUES (%s,%s,%s,%s,%s)""",
                chunks,
            )

    return {"node": len(rows), "chunk": len(chunks)}

"""Hybrid search goi tim_kiem_hybrid() tren DB."""
from __future__ import annotations

from datetime import date
from typing import Any

from psycopg import Connection

from app.core.models.embedder import embed


def tim_hybrid(
    conn: Connection, q_text: str, q_embedding: list[float],
    top_k: int = 20, ngay: date | None = None,
    cap_max: int | None = None, van_ban_ids: list[str] | None = None,
    linh_vuc: list[str] | None = None,
) -> list[dict[str, Any]]:
    emb_str = "[" + ",".join(f"{x:.6f}" for x in q_embedding) + "]"
    with conn.cursor() as cur:
        cur.execute(
            """SELECT chunk_id, diem_rrf
               FROM tim_kiem_hybrid(%s::vector, %s, %s, %s, %s, %s, %s)""",
            (emb_str, q_text, top_k, ngay or date.today(), cap_max,
             van_ban_ids, linh_vuc),
        )
        return [{"chunk_id": r[0], "diem_rrf": float(r[1])} for r in cur.fetchall()]


def tim_hybrid_tu_text(
    conn: Connection, text: str, ngay: date | None = None,
    cap_max: int | None = None, van_ban_ids: list[str] | None = None,
    linh_vuc: list[str] | None = None, nguong: float = 0.0, top_k: int = 20,
) -> list[dict[str, Any]]:
    emb = embed(text[:2000])
    rows = tim_hybrid(conn, text, emb, top_k=top_k, ngay=ngay,
                      cap_max=cap_max, van_ban_ids=van_ban_ids, linh_vuc=linh_vuc)
    rows = [r for r in rows if r["diem_rrf"] >= nguong]
    # Lam giau: tim van ban cua chunk de dua vao parent_docs
    if not rows:
        return rows
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, van_ban_id, dieu_id FROM chunk WHERE id = ANY(%s)",
            ([r["chunk_id"] for r in rows],),
        )
        meta = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    for r in rows:
        vb, dieu = meta.get(r["chunk_id"], (None, None))
        r["van_ban_id"] = vb
        r["dieu_id"] = dieu
    return rows

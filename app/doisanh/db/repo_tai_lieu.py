"""Repository kho du thao: du_thao (van ban + cay JSON) + du_thao_node (chunk + text_embed + vector).

User chi upload file, khong cung cap metadata. Cay da segment luu nguyen o du_thao.cay (JSON goc);
du_thao_node la kho chunk de embed + doi sanh (doi xung van_ban -> node/chunk cua kho luat).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from psycopg import Connection
from psycopg.types.json import Json

from app.core.config import settings
from app.core.models.embedder import embed_batch
from app.doisanh.audit.segment import KetQuaSegment


def sinh_id_tai_lieu() -> str:
    return "TL-" + uuid.uuid4().hex[:8]


def _text_embed(tieu_de: str | None, noi_dung: str) -> str:
    """Text dua di embed = '<tieu_de>. <noi_dung>' (giong _chunk_embed_text o routes_simple)."""
    return (tieu_de + ". " + noi_dung) if tieu_de else (noi_dung or "")


def luu_du_thao(conn: Connection, du_thao_id: str, noi_dung: str, seg: KetQuaSegment) -> None:
    """Luu toan van + cay JSON vao du_thao, va bung tung don vi ra du_thao_node. Idempotent theo id."""
    cay = {
        "don_vi": [asdict(dv) for dv in seg.don_vi],
        "can_cu_tho": seg.can_cu_tho,
        "co_cau_truc_dieu": seg.co_cau_truc_dieu,
    }
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO du_thao (id, noi_dung, cay) VALUES (%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET noi_dung=EXCLUDED.noi_dung, cay=EXCLUDED.cay""",
            (du_thao_id, noi_dung, Json(cay)),
        )
        # Dung lai node cu (chunk CASCADE) roi nap lai -> idempotent.
        cur.execute("DELETE FROM du_thao_node WHERE du_thao_id=%s", (du_thao_id,))
        cur.executemany(
            """INSERT INTO du_thao_node
                 (id, du_thao_id, parent_id, cap, so_dieu, so_khoan, diem, tieu_de,
                  noi_dung, thu_tu, text_embed)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(dv.id, du_thao_id, dv.parent_id, dv.cap, dv.so_dieu, dv.so_khoan, dv.diem,
              dv.tieu_de, dv.noi_dung, dv.thu_tu, _text_embed(dv.tieu_de, dv.noi_dung))
             for dv in seg.don_vi],
        )


def nhung_du_thao_thieu(conn: Connection, du_thao_id: str, batch_size: int | None = None) -> int:
    """Sinh embedding cho du_thao_node co embedding IS NULL (tu text_embed). Idempotent.

    Doi xung public_loader.nhung_chunk_thieu cua kho luat.
    """
    bs = batch_size or settings.EMBED_BATCH_SIZE
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, text_embed FROM du_thao_node "
            "WHERE du_thao_id=%s AND embedding IS NULL AND text_embed <> '' ORDER BY thu_tu",
            (du_thao_id,),
        )
        rows = cur.fetchall()
    da = 0
    for i in range(0, len(rows), bs):
        lo = rows[i : i + bs]
        embs = embed_batch([t for _, t in lo])
        with conn.cursor() as cur:
            for (nid, _), emb in zip(lo, embs):
                if len(emb) != settings.EMBED_DIM:
                    raise ValueError(f"node {nid}: embedding {len(emb)}d != EMBED_DIM {settings.EMBED_DIM}")
                emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
                cur.execute("UPDATE du_thao_node SET embedding=%s::vector WHERE id=%s", (emb_str, nid))
        conn.commit()
        da += len(lo)
    return da


def doc_du_thao(conn: Connection, du_thao_id: str) -> dict[str, Any] | None:
    """Thong tin van ban du thao tu du_thao.cay (None neu chua co). Don vi lay o danh_sach_don_vi."""
    with conn.cursor() as cur:
        cur.execute("SELECT noi_dung, cay FROM du_thao WHERE id=%s", (du_thao_id,))
        row = cur.fetchone()
    if row is None:
        return None
    noi_dung, cay = row
    cay = cay or {}
    return {
        "noi_dung": noi_dung,
        "can_cu_tho": cay.get("can_cu_tho", []),
        "co_cau_truc_dieu": cay.get("co_cau_truc_dieu", False),
    }


def danh_sach_don_vi(conn: Connection, du_thao_id: str) -> list[dict[str, Any]]:
    """Don vi du thao tu du_thao_node, kem embedding (text) de /audit dung lai khoi embed lai."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, parent_id, cap, so_dieu, so_khoan, diem, tieu_de, noi_dung,
                      thu_tu, embedding::text AS embedding
               FROM du_thao_node WHERE du_thao_id=%s ORDER BY thu_tu""",
            (du_thao_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def xoa_du_thao(conn: Connection, du_thao_id: str) -> int:
    """Xoa 1 du thao (du_thao_node cascade theo FK). Tra so dong du_thao da xoa (0/1)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM du_thao WHERE id=%s", (du_thao_id,))
        return cur.rowcount


def xoa_tat_ca_du_thao(conn: Connection) -> int:
    """Xoa TAT CA du thao (clear kho rag du thao). Tra so dong da xoa."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM du_thao")
        return cur.rowcount

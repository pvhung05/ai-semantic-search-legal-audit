"""Tao chunk + embedding cho moi Khoan/Dieu de ho tro truy hoi hybrid (GD E).

chunk.id = khoan.id (khi co Khoan) hoac dieu_luat.id (Dieu khong chia Khoan).
Ke thua hieu luc tu Dieu/Khoan.
"""
from __future__ import annotations

import logging

from psycopg import Connection

from app.models.embedder import embed_batch

logger = logging.getLogger(__name__)


def _bundle_text(dieu_tieu_de: str | None, noi_dung: str) -> str:
    tt = (dieu_tieu_de or "").strip()
    return (tt + "\n" + noi_dung).strip() if tt else noi_dung


def tao_chunks_cho_van_ban(conn: Connection, van_ban_id: str, batch_size: int = 32) -> int:
    """Dung Khoan khi co, nguoc lai dung Dieu. Chen embedding batch."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.id, d.tieu_de, v.cap, d.noi_dung, d.hieu_luc_tu, d.hieu_luc_den, v.linh_vuc
               FROM dieu_luat d JOIN van_ban v ON v.id = d.van_ban_id
               WHERE d.van_ban_id=%s AND d.trang_thai <> 'bai_bo'
                 AND NOT EXISTS (SELECT 1 FROM khoan k WHERE k.dieu_id = d.id)""",
            (van_ban_id,),
        )
        dieu_rows = cur.fetchall()
        cur.execute(
            """SELECT k.id, k.dieu_id, d.tieu_de, v.cap, k.noi_dung,
                      k.hieu_luc_tu, k.hieu_luc_den, v.linh_vuc,
                      k.diem, p.noi_dung AS parent_noi_dung
               FROM khoan k JOIN dieu_luat d ON d.id = k.dieu_id
               JOIN van_ban v ON v.id = k.van_ban_id
               LEFT JOIN khoan p ON p.id = k.parent_id
               WHERE k.van_ban_id=%s AND k.trang_thai <> 'bai_bo'""",
            (van_ban_id,),
        )
        khoan_rows = cur.fetchall()

    chunks_meta: list[tuple] = []
    texts: list[str] = []
    for row in khoan_rows:
        (kid, dieu_id, tieu_de, cap, noi_dung, hl_tu, hl_den, linh_vuc,
         diem, parent_noi_dung) = row
        if diem is not None:
            # Diem: text embed = Khoan cha noi_dung + Diem noi_dung
            text = _bundle_text(parent_noi_dung or tieu_de, noi_dung or "")
        else:
            # Khoan khong co Diem (hoac Khoan cha cua Diem): text = tieu_de Dieu + Khoan
            text = _bundle_text(tieu_de, noi_dung or "")
        chunks_meta.append((kid, dieu_id, kid, van_ban_id, cap, linh_vuc or [],
                            hl_tu, hl_den, noi_dung or "", text))
        texts.append(text)
    for did, tieu_de, cap, noi_dung, hl_tu, hl_den, lv in dieu_rows:
        text = _bundle_text(tieu_de, noi_dung or "")
        chunks_meta.append((did, did, None, van_ban_id, cap, lv or [],
                            hl_tu, hl_den, noi_dung or "", text))
        texts.append(text)

    if not chunks_meta:
        return 0

    embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings.extend(embed_batch(batch))

    with conn.cursor() as cur:
        for meta, emb in zip(chunks_meta, embeddings):
            (cid, dieu_id, khoan_id_val, vb_id, cap, lv, hl_tu, hl_den,
             text_goc, text_embed) = meta
            emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
            cur.execute(
                """INSERT INTO chunk (id, dieu_id, khoan_id, van_ban_id, cap, linh_vuc,
                                        hieu_luc_tu, hieu_luc_den, text_goc, text_embed, embedding)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                   ON CONFLICT (id) DO UPDATE SET
                     hieu_luc_tu=EXCLUDED.hieu_luc_tu, hieu_luc_den=EXCLUDED.hieu_luc_den,
                     text_goc=EXCLUDED.text_goc, text_embed=EXCLUDED.text_embed,
                     embedding=EXCLUDED.embedding""",
                (cid, dieu_id, khoan_id_val, vb_id, cap, lv, hl_tu, hl_den,
                 text_goc, text_embed, emb_str),
            )
    return len(chunks_meta)

"""Hoi-dap kieu RAG: hybrid search tren bang chunk -> LLM tra loi co trich dan.

Luong:
1. Embed cau hoi + hybrid search (vector + BM25) qua tim_hybrid_tu_text.
2. Nap chi tiet Khoan/Dieu/Van ban cua top-k ket qua.
3. Dong goi vao prompt, yeu cau LLM tra loi va chi ra chi muc [1], [2]...
4. Tra ve {tra_loi, can_cu: [{so_hieu, dieu, khoan, diem, trich_dan, van_ban_id, khoan_id}]}.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from psycopg import Connection

from app.models.llm import goi_chat
from app.retrieval.hybrid import tim_hybrid_tu_text

logger = logging.getLogger(__name__)


@dataclass
class CanCuTraLoi:
    so_tt: int
    van_ban_id: str
    so_hieu: str
    ten_van_ban: str
    so_dieu: str | None
    so_khoan: str | None
    diem: str | None
    trich_dan: str
    diem_rrf: float


def _nap_chi_tiet(
    conn: Connection, chunks: list[dict[str, Any]],
) -> list[CanCuTraLoi]:
    """Join chunk -> khoan + dieu_luat + van_ban de lay thong tin trich dan."""
    if not chunks:
        return []
    chunk_ids = [c["chunk_id"] for c in chunks]
    diem_map = {c["chunk_id"]: c["diem_rrf"] for c in chunks}
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.id, v.id, v.so_hieu, v.ten,
                      d.so_dieu, k.so_khoan, k.diem,
                      COALESCE(k.noi_dung, d.noi_dung, c.text_goc)
               FROM chunk c
               JOIN van_ban v ON v.id = c.van_ban_id
               LEFT JOIN dieu_luat d ON d.id = c.dieu_id
               LEFT JOIN khoan k ON k.id = c.khoan_id
               WHERE c.id = ANY(%s)""",
            (chunk_ids,),
        )
        rows = cur.fetchall()
    rows_by_id = {r[0]: r for r in rows}
    ket: list[CanCuTraLoi] = []
    for i, cid in enumerate(chunk_ids, 1):
        r = rows_by_id.get(cid)
        if not r:
            continue
        _, vb_id, so_hieu, ten, sd, sk, dm, trich = r
        ket.append(CanCuTraLoi(
            so_tt=i, van_ban_id=vb_id, so_hieu=so_hieu or "", ten_van_ban=ten or "",
            so_dieu=sd, so_khoan=sk, diem=dm,
            trich_dan=(trich or "").strip(),
            diem_rrf=diem_map.get(cid, 0.0),
        ))
    return ket


def _dinh_dang_can_cu(can_cu: list[CanCuTraLoi], max_char: int = 600) -> str:
    khoi = []
    for c in can_cu:
        vi_tri = c.so_hieu
        if c.so_dieu:
            vi_tri += f", Dieu {c.so_dieu}"
        if c.so_khoan:
            vi_tri += f", Khoan {c.so_khoan}"
        if c.diem:
            vi_tri += f", Diem {c.diem}"
        trich = c.trich_dan[:max_char]
        khoi.append(f"[{c.so_tt}] {vi_tri}\n{trich}")
    return "\n\n".join(khoi)


SYSTEM_PROMPT = (
    "Ban la tro ly phap luat Viet Nam. Chi tra loi dua tren cac CAN CU duoc cung cap. "
    "Khi dan chieu, dung ky hieu [so] theo thu tu can cu (vi du [1], [2]). "
    "Neu can cu khong du de tra loi, noi ro 'Toi khong co du can cu' va liet ke phan thieu. "
    "KHONG bia noi dung luat ngoai can cu da cho. Tra loi bang tieng Viet, ngan gon, co cau truc."
)


def hoi_dap(
    conn: Connection, cau_hoi: str,
    top_k: int = 8, ngay: date | None = None,
    van_ban_ids: list[str] | None = None, linh_vuc: list[str] | None = None,
    cap_max: int | None = None, nguong_rrf: float = 0.0,
    is_local: bool | None = None,
) -> dict[str, Any]:
    """Tra ve {tra_loi, can_cu, so_can_cu}. Rong neu khong tim thay chunk nao."""
    cau_hoi = cau_hoi.strip()
    if not cau_hoi:
        return {"tra_loi": "", "can_cu": [], "so_can_cu": 0}
    rows = tim_hybrid_tu_text(
        conn, cau_hoi, ngay=ngay, cap_max=cap_max,
        van_ban_ids=van_ban_ids, linh_vuc=linh_vuc,
        nguong=nguong_rrf, top_k=top_k,
    )
    if not rows:
        return {
            "tra_loi": "Toi khong tim thay can cu phap ly phu hop trong kho du lieu.",
            "can_cu": [], "so_can_cu": 0,
        }
    can_cu = _nap_chi_tiet(conn, rows)
    if not can_cu:
        return {
            "tra_loi": "Toi khong tim thay can cu phap ly phu hop trong kho du lieu.",
            "can_cu": [], "so_can_cu": 0,
        }
    khoi_can_cu = _dinh_dang_can_cu(can_cu)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"CAU HOI: {cau_hoi}\n\n"
            f"CAC CAN CU PHAP LY (top-{len(can_cu)} khoan lien quan):\n{khoi_can_cu}\n\n"
            "Hay tra loi cau hoi dua tren cac can cu tren, co chi muc [so]."
        )},
    ]
    tra_loi = goi_chat(messages, temperature=0.1, is_local=is_local)
    return {
        "tra_loi": tra_loi.strip(),
        "can_cu": [
            {
                "so_tt": c.so_tt, "van_ban_id": c.van_ban_id, "so_hieu": c.so_hieu,
                "ten_van_ban": c.ten_van_ban, "so_dieu": c.so_dieu,
                "so_khoan": c.so_khoan, "diem": c.diem,
                "trich_dan": c.trich_dan, "diem_rrf": round(c.diem_rrf, 4),
            }
            for c in can_cu
        ],
        "so_can_cu": len(can_cu),
    }

"""Hoi-dap kieu RAG: hybrid search -> dung can cu GIONG /audit -> LLM tra loi co trich dan.

Luong:
1. Embed cau hoi + hybrid search (vector + BM25) qua tim_hybrid_tu_text.
2. Gom ket qua ve Khoan me qua nap_khoan_ung_vien (ca Khoan + Phan/Chuong + tac dong) - chung voi /audit.
3. Dong goi vao prompt, yeu cau LLM tra loi va chi ra chi muc [1], [2]...
4. Tra ve {tra_loi, can_cu: [{so_hieu, phan, chuong, so_dieu, khoan, trich_dan, da_sua, ...}]}.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from psycopg import Connection

from app.core.models.llm import goi_chat
from app.doisanh.public_loader import tac_dong_tom_tat
from app.doisanh.retrieval.can_cu import nap_khoan_ung_vien
from app.doisanh.retrieval.hybrid import tim_hybrid_tu_text

logger = logging.getLogger(__name__)


def _vi_tri(u: dict) -> str:
    """Vi tri can cu: 'Phan.. Chuong.. Dieu X khoan Y' tu ung vien (giong /audit)."""
    parts = []
    for k in ("phan", "chuong"):
        if u.get(k):
            parts.append(u[k])
    if u.get("so_dieu"):
        parts.append(f"Điều {u['so_dieu']}")
    if u.get("so_khoan"):
        parts.append(f"khoản {u['so_khoan']}")
    if u.get("diem"):
        parts.append(f"điểm {u['diem']}")
    return " ".join(parts) or (u.get("so_hieu") or "")


def _dinh_dang_can_cu(ung_vien: list[dict], max_char: int = 1200) -> str:
    """Dong goi can cu cho prompt. noi_dung da co khoi 'noi dung sau khi sua' o dau (neu bi tac dong)."""
    khoi = []
    for i, u in enumerate(ung_vien, 1):
        vi_tri = u.get("so_hieu", "")
        chi_tiet = _vi_tri(u)
        tieu = f"{vi_tri} — {chi_tiet}" if chi_tiet else vi_tri
        khoi.append(f"[{i}] {tieu}\n{(u.get('noi_dung') or '')[:max_char]}")
    return "\n\n".join(khoi)


SYSTEM_PROMPT = (
    "Ban la chuyen vien tham dinh phap luat Viet Nam. Dua tren cac CAN CU duoc cung cap, "
    "hay danh gia noi dung nguoi dung neu trong CAU HOI theo DUNG cau truc sau:\n"
    "1. KET LUAN: mot trong 'Đúng' | 'Sai' | 'Chưa đủ căn cứ'.\n"
    "   - Đúng = noi dung PHU HOP voi quy dinh phap luat trong can cu.\n"
    "   - Sai = noi dung TRAI / vi pham quy dinh phap luat trong can cu.\n"
    "   - Chưa đủ căn cứ = cac can cu khong du de ket luan.\n"
    "2. GIAI THICH: ngan gon, chi ro diem dung/sai, moi y dan chieu [so] theo thu tu can cu.\n"
    "3. CAN CU PHAP LY: liet ke [so] cac can cu da dung.\n"
    "KHONG bia noi dung luat ngoai can cu da cho. Tra loi bang tieng Viet, ngan gon. "
    "LUU Y TAC DONG: neu mot can cu mo dau bang khoi '[CAN CU NAY ... DUNG NOI DUNG SAU KHI SUA "
    "LAM CHUAN]' kem dong 'Noi dung sau khi sua: ...' -> PHAI danh gia theo NOI DUNG SAU KHI SUA "
    "va noi ro can cu do da duoc sua doi (boi van ban/dieu khoan ghi trong khoi). Neu khoi ghi "
    "'DA HET HIEU LUC' (bai bo) -> can cu do khong con hieu luc, phai canh bao nguoi dung."
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
    rong = {
        "tra_loi": "Toi khong tim thay can cu phap ly phu hop trong kho du lieu.",
        "can_cu": [], "so_can_cu": 0,
    }
    rows = tim_hybrid_tu_text(
        conn, cau_hoi, ngay=ngay, cap_max=cap_max,
        van_ban_ids=van_ban_ids, linh_vuc=linh_vuc,
        nguong=nguong_rrf, top_k=top_k,
    )
    if not rows:
        return rong
    # Dung can cu GIONG /audit: gom ve Khoan me (ca Khoan + Phan/Chuong + tac dong da ap).
    diem_rrf = {r["chunk_id"]: r["diem_rrf"] for r in rows}
    ung_vien = nap_khoan_ung_vien(conn, [r["chunk_id"] for r in rows], diem_rrf)
    if not ung_vien:
        return rong

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"CAU HOI: {cau_hoi}\n\n"
            f"CAC CAN CU PHAP LY (top-{len(ung_vien)} khoan lien quan):\n"
            f"{_dinh_dang_can_cu(ung_vien)}\n\n"
            "Hay danh gia noi dung CAU HOI: mo dau bang 'KET LUAN: Đúng/Sai/Chưa đủ căn cứ', "
            "sau do GIAI THICH va CAN CU PHAP LY co chi muc [so]."
        )},
    ]
    tra_loi = goi_chat(messages, temperature=0.1, is_local=is_local)
    ngay_iso = (ngay or date.today()).isoformat()
    return {
        "tra_loi": tra_loi.strip(),
        "can_cu": [
            {
                "so_tt": i, "van_ban_id": u["van_ban_id"], "so_hieu": u["so_hieu"],
                "ten_van_ban": u["ten_van_ban"],
                "phan": u.get("phan"), "chuong": u.get("chuong"),
                "so_dieu": u["so_dieu"], "so_khoan": u["so_khoan"], "diem": u["diem"],
                "trich_dan": u["noi_dung"], "diem_rrf": round(u["diem_rrf"], 4),
                "da_sua": tac_dong_tom_tat(u.get("tac_dong"), ngay_iso) if u.get("tac_dong") else None,
            }
            for i, u in enumerate(ung_vien, 1)
        ],
        "so_can_cu": len(ung_vien),
    }

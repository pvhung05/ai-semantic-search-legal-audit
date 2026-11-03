"""Fallback cho Dieu mo coi.

- ENABLE_FALLBACK=false: ghi khong_co_can_cu_uy_quyen (muc_do trung_binh).
- ENABLE_FALLBACK=true (GD E): embed + tim_kiem_hybrid -> anh xa 'truy_hoi' -> tier2 tang=3.
"""
from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.doisanh.audit.segment import DonViSegment
from app.core.config import settings
from app.core.models.schemas import PhatHien


def phat_hien_mo_coi_khong_can_cu(dv: DonViSegment) -> PhatHien:
    return PhatHien(
        don_vi_id=dv.id, tang=3, loai_loi="khong_co_can_cu_uy_quyen",
        muc_do="trung_binh", tin_cay=0.6,
        doan_du_thao=dv.noi_dung[:400],
        giai_thich=(
            "Khong anh xa duoc toi van ban me nao; can ra soat thu cong "
            "xem Dieu nay co can cu uy quyen phap ly khong."
        ),
    )


def truy_hoi_dieu_mo_coi(
    conn: Connection, dv: DonViSegment, ngay, cap_du_thao: int | None,
) -> list[dict[str, Any]]:
    """GD E: tra chunk ung vien cho Dieu mo coi (hybrid).

    Can app/retrieval/hybrid.py va chunks da embed. Mac dinh tat.
    """
    if not settings.ENABLE_FALLBACK:
        return []
    try:
        from app.doisanh.retrieval.hybrid import tim_hybrid_tu_text
    except ImportError:
        return []
    cap_max = (cap_du_thao - 1) if cap_du_thao else None
    return tim_hybrid_tu_text(
        conn, text=dv.noi_dung, ngay=ngay, cap_max=cap_max,
        nguong=settings.AUDIT_NGUONG_FALLBACK,
    )

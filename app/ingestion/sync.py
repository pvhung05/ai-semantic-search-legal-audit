"""Thi hanh lenh sua doi chua ap dung, cap nhat trang thai van ban."""
from __future__ import annotations

from app.db.repo_hieu_luc import thi_hanh_lenh_chua_ap_dung
from app.db.session import ket_noi


def dong_bo_hieu_luc() -> list[dict]:
    """Thi hanh moi lenh da_ap_dung=false; chay lai idempotent."""
    with ket_noi() as conn:
        return thi_hanh_lenh_chua_ap_dung(conn)

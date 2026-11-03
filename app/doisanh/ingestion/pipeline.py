"""Pipeline nap mot van ban luat vao DB.

Luong: load -> normalize -> parse -> summarize -> upsert van_ban/dieu/khoan.
Idempotent qua UPSERT. GD B them: trich lenh sua doi khi la_van_ban_sua_doi.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.doisanh.db import repo_van_ban as repo
from app.core.db.session import ket_noi
from app.doisanh.ingestion.loader import doc_file
from app.doisanh.ingestion.parser import parse_van_ban
from app.doisanh.ingestion.summarize import tom_tat_dieu
from app.core.models.schemas import VanBanMeta, VanBanParsed

logger = logging.getLogger(__name__)


def nap_van_ban(
    file_path: Path,
    meta: VanBanMeta,
    hieu_luc_tu: date | None = None,
    chay_tom_tat: bool = True,
) -> dict:
    """Nap mot van ban luat tu file vao DB.

    Tra: {'van_ban_id': ..., 'so_dieu': ..., 'so_khoan': ..., 'canh_bao': [...]}.
    """
    file_path = Path(file_path)
    logger.info("Nap van ban %s tu %s", meta.id, file_path)

    text = doc_file(file_path)
    meta_voi_nguon = meta.model_copy(update={"nguon_file": str(file_path)})
    parsed = parse_van_ban(text, meta_voi_nguon)

    if chay_tom_tat and parsed.dieu:
        tom_tat_dieu(parsed.dieu)

    with ket_noi() as conn:
        thong_ke = repo.luu_van_ban_day_du(conn, parsed, hieu_luc_tu=hieu_luc_tu)
        # GD B4: rut quan he can_cu + quy_dinh_chi_tiet
        from app.doisanh.ingestion.quan_he import ghi_can_cu, ghi_quy_dinh_chi_tiet
        thong_ke["so_can_cu"] = ghi_can_cu(conn, parsed.meta.id, parsed.can_cu_tho)
        thong_ke["so_qdct"] = ghi_quy_dinh_chi_tiet(conn, parsed.meta.id, parsed.meta.ten)
        conn.commit()

    # GD B: parse lenh sua doi neu la van ban sua doi
    if parsed.meta.la_van_ban_sua_doi:
        try:
            from app.doisanh.ingestion.amend_parser import parse_lenh_sua_doi, luu_lenh_sua_doi
            lenh = parse_lenh_sua_doi(parsed)
            with ket_noi() as conn:
                luu_lenh_sua_doi(conn, parsed.meta.id, lenh)
                conn.commit()
            thong_ke["so_lenh_sua_doi"] = len(lenh)
        except ImportError:
            logger.info("amend_parser chua co, bo qua trich lenh sua doi")

    # GD B: trich dan chieu luat trong moi Khoan
    try:
        from app.doisanh.ingestion.citation_parser import ghi_dan_chieu_cho_van_ban
        with ket_noi() as conn:
            so_dc = ghi_dan_chieu_cho_van_ban(conn, parsed.meta.id)
            conn.commit()
        thong_ke["so_dan_chieu"] = so_dc
    except ImportError:
        pass

    return {
        "van_ban_id": parsed.meta.id,
        **thong_ke,
        "canh_bao": parsed.canh_bao,
    }


def parse_file(file_path: Path, meta: VanBanMeta) -> VanBanParsed:
    """Chi parse khong luu DB (de test)."""
    text = doc_file(Path(file_path))
    return parse_van_ban(text, meta)

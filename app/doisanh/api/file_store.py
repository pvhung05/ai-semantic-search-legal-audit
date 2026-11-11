"""Luu/doc file du thao goc va file track-change tren dia. Tach khoi route."""
from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings

DRAFT_DIR = settings.STORAGE_PATH / "drafts"               # ban goc du thao (giu ten upload)
OUTPUT_DIR = settings.STORAGE_PATH.parent / "track_changes"  # = data/track_changes: ban da track-change
HAU_TO_TC = "_track_changes"


def luu_file_goc(tai_lieu_id: str, src: Path, ten_goc: str | None) -> None:
    """Luu ban goc giu nguyen TEN FILE upload (de dat ten ban track-change sau)."""
    folder = DRAFT_DIR / tai_lieu_id
    folder.mkdir(parents=True, exist_ok=True)
    ten = Path(ten_goc or f"du_thao{src.suffix}").name
    shutil.copy(src, folder / ten)


def file_goc(tai_lieu_id: str) -> Path | None:
    """File goc du thao da luu luc upload (moi folder chi co 1 file).

    Output track-change nam o OUTPUT_DIR (thu muc khac), nen o day khong can
    loai tru *_track_changes: cu tra file dau tien tim thay.
    """
    folder = DRAFT_DIR / tai_lieu_id
    if not folder.is_dir():
        return None
    for f in folder.iterdir():
        if f.is_file():
            return f
    return None


def duong_dan_output(tai_lieu_id: str, src_stem: str) -> Path:
    """Duong dan file track-change '<ten_goc>_track_changes.docx' (tao thu muc neu thieu)."""
    out_dir = OUTPUT_DIR / tai_lieu_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{src_stem}{HAU_TO_TC}.docx"


def tim_file_track_change(tai_lieu_id: str) -> Path | None:
    """File track-change da tao o POST /audit/docx (data/track_changes)."""
    folder = OUTPUT_DIR / tai_lieu_id
    hits = sorted(folder.glob(f"*{HAU_TO_TC}.docx")) if folder.is_dir() else []
    return hits[0] if hits else None


def xoa_tat_ca_file() -> None:
    shutil.rmtree(DRAFT_DIR, ignore_errors=True)
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


def xoa_file(tai_lieu_id: str) -> None:
    shutil.rmtree(DRAFT_DIR / tai_lieu_id, ignore_errors=True)
    shutil.rmtree(OUTPUT_DIR / tai_lieu_id, ignore_errors=True)

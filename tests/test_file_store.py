from pathlib import Path
import pytest
from app.doisanh.api import file_store


def test_la_id_hop_le():
    assert file_store.la_id_hop_le("TL-a1b2c3d4") is True
    assert file_store.la_id_hop_le("draft_123-abc") is True
    assert file_store.la_id_hop_le("12345") is True

    # Khong hop le (path traversal hoac ky tu la)
    assert file_store.la_id_hop_le("..") is False
    assert file_store.la_id_hop_le("../../etc") is False
    assert file_store.la_id_hop_le("a/b") is False
    assert file_store.la_id_hop_le("a\\b") is False
    assert file_store.la_id_hop_le("") is False
    assert file_store.la_id_hop_le("   ") is False


def test_file_store_luu_doc_xoa(tmp_path, monkeypatch):
    monkeypatch.setattr(file_store, "DRAFT_DIR", tmp_path / "drafts")
    monkeypatch.setattr(file_store, "OUTPUT_DIR", tmp_path / "track_changes")

    dummy_file = tmp_path / "test.docx"
    dummy_file.write_text("dummy content", encoding="utf-8")

    tai_lieu_id = "TL-test01"
    file_store.luu_file_goc(tai_lieu_id, dummy_file, "original.docx")

    saved = file_store.file_goc(tai_lieu_id)
    assert saved is not None
    assert saved.name == "original.docx"
    assert saved.read_text(encoding="utf-8") == "dummy content"

    # Xoa an toan
    file_store.xoa_file(tai_lieu_id)
    assert file_store.file_goc(tai_lieu_id) is None


def test_luu_file_goc_chan_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(file_store, "DRAFT_DIR", tmp_path / "drafts")
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="tai_lieu_id khong hop le"):
        file_store.luu_file_goc("../bad", dummy_file, "x.txt")

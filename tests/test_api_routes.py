from typing import Any, Coroutine
import pytest
from fastapi import HTTPException

from app.doisanh.api.main import healthz, home
from app.doisanh.api import routes_simple
from app.doisanh.api.routes_simple import (
    AuditRequest,
    tai_file_track_changes,
    upload_draft,
    upload_legal,
    xoa_draft,
)


def _chay_coro(coro: Coroutine) -> Any:
    """Chay coroutine don gian offline ma khong can khoi tao event loop / socket loopback."""
    gen = coro.__await__()
    val = None
    while True:
        try:
            sub = gen.send(val)
            if hasattr(sub, "__await__"):
                val = _chay_coro(sub)
            else:
                val = sub
        except StopIteration as e:
            return e.value


def test_healthz_endpoint():
    assert healthz() == {"status": "ok"}


def test_spa_home_endpoint():
    res = home()
    assert "audit-legal" in res


def test_upload_legal_tra_ve_501():
    with pytest.raises(HTTPException) as exc:
        _chay_coro(upload_legal(None, ""))
    assert exc.value.status_code == 501
    assert "chưa hỗ trợ" in exc.value.detail


def test_upload_draft_file_qua_lon(monkeypatch):
    monkeypatch.setattr(routes_simple, "MAX_UPLOAD_SIZE", 100)

    class MockUploadFile:
        filename = "test.docx"

        async def read(self):
            return b"x" * 150

    with pytest.raises(HTTPException) as exc:
        _chay_coro(upload_draft(MockUploadFile()))
    assert exc.value.status_code == 413
    assert "vượt quá giới hạn" in exc.value.detail


def test_audit_invalid_tai_lieu_id_pattern():
    with pytest.raises(ValueError):
        AuditRequest(tai_lieu_id="../../bad_id")
    req = AuditRequest(tai_lieu_id="TL-valid_id-1")
    assert req.tai_lieu_id == "TL-valid_id-1"


def test_xoa_draft_invalid_id():
    with pytest.raises(HTTPException) as exc:
        xoa_draft("bad..id")
    assert exc.value.status_code == 400
    assert "khong hop le" in exc.value.detail


def test_tai_file_track_changes_invalid_id():
    with pytest.raises(HTTPException) as exc:
        tai_file_track_changes("bad..id")
    assert exc.value.status_code == 400
    assert "khong hop le" in exc.value.detail



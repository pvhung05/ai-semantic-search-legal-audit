"""Nhanh fallback cua rerank (khong goi mang)."""
from app.core.config import settings
from app.doisanh.retrieval import rerank as rr


def test_rerank_tat_khi_khong_co_url(monkeypatch):
    monkeypatch.setattr(settings, "RERANK_URL", "")
    uv = [{"noi_dung": f"n{i}"} for i in range(10)]
    out = rr.rerank("q", uv, 5)
    assert [u["noi_dung"] for u in out] == [f"n{i}" for i in range(5)]  # giu thu tu, cat top_n


def test_rerank_bo_qua_khi_it_hon_top_n(monkeypatch):
    monkeypatch.setattr(settings, "RERANK_URL", "http://x")  # co URL nhung khong goi mang
    uv = [{"noi_dung": "a"}, {"noi_dung": "b"}]
    assert rr.rerank("q", uv, 5) == uv   # len(uv) <= top_n -> khong goi service


def test_rerank_loi_goi_tra_fallback(monkeypatch):
    monkeypatch.setattr(settings, "RERANK_URL", "http://127.0.0.1:9/rerank")  # cong chet
    uv = [{"noi_dung": f"n{i}"} for i in range(8)]
    out = rr.rerank("q", uv, 3)
    assert len(out) == 3 and out[0]["noi_dung"] == "n0"  # loi -> giu thu tu hybrid

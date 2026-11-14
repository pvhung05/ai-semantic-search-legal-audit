"""Rerank ung vien bang cross-encoder qua TEI /rerank (BAAI/bge-reranker-v2-m3).

Request:  {"query": str, "texts": [str,...], "truncate": true}
Response: [{"index": i, "score": float}, ...]  sap theo score giam dan.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_CHAR = 4000   # cat text truoc khi gui (server van tu truncate theo token)
_RERANK_CLIENT: httpx.Client | None = None


def _lay_rerank_client() -> httpx.Client:
    global _RERANK_CLIENT
    if _RERANK_CLIENT is None or _RERANK_CLIENT.is_closed:
        _RERANK_CLIENT = httpx.Client(timeout=30)
    return _RERANK_CLIENT


def rerank(query: str, ung_vien: list[dict], top_n: int, *, khoa_text: str = "noi_dung") -> list[dict]:
    """Sap xep lai ung_vien theo do lien quan voi query (cross-encoder), lay top_n.

    Khong cau hinh RERANK_URL / <= top_n ung vien / loi goi -> fallback: giu thu tu
    hybrid hien tai, cat top_n. Gan 'rerank_score' vao ung vien duoc chon.
    """
    if not settings.RERANK_URL or len(ung_vien) <= top_n:
        return ung_vien[:top_n]
    texts = [(u.get(khoa_text) or "")[:_MAX_CHAR] for u in ung_vien]
    try:
        cli = _lay_rerank_client()
        r = cli.post(
            settings.RERANK_URL,
            json={"query": (query or "")[:_MAX_CHAR], "texts": texts, "truncate": True},
        )
        r.raise_for_status()
        ket_qua = r.json()
    except Exception as exc:
        logger.warning("Rerank loi (%s) -> giu thu tu hybrid", exc)
        return ung_vien[:top_n]

    out: list[dict] = []
    for item in ket_qua[:top_n]:
        i = item.get("index")
        if isinstance(i, int) and 0 <= i < len(ung_vien):
            u = ung_vien[i]
            u["rerank_score"] = item.get("score")
            out.append(u)
    return out or ung_vien[:top_n]

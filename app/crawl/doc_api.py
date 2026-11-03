"""Fetch + parse 5 API chi tiet van ban cua vbpl.vn (JSON sach).

Moi API la mot Server Action POST voi body ["<id>"]. Response text/x-component.
Day la nguon metadata chinh thuc (thay cho viec scrape chunk tu HTML SSR).

  doc_info  (0fb12b35): JSON thong tin van ban, nam sau '</html>1:' o cuoi response.
  luoc_do   (4a3423ce): dong '1:{documentNamesByType, documentNamesBySource}'.
  lich_su   (fe4862cb): dong '1:[...]' danh sach lifecycle + tac dong hieu luc.
  vbhn      (0932c380): dong '1:[...]' nhom van ban hop nhat.
  toan_van  (233848b4): HTML giua <html>...</html>.
"""
from __future__ import annotations

import json
import re

from .fetcher import BASE, Fetcher
from .parser import parse_rsc_flight, parse_rsc_payload, resolve_rsc_refs

ACTIONS = {
    "doc_info": "0fb12b3561faa05adec51a82efb3e4f4f427f07b",
    "luoc_do":  "4a3423ce75290ef83a022333ee187acf4d38d3fb",
    "lich_su":  "fe4862cb550ced8ac0057edfdf498bca2229be52",
    "vbhn":     "0932c3801e9e99306fe7e694562e44ba55134662",
    "toan_van": "233848b47c25357313670674c2dc84e482ce54da",
    "cay":      "31572a1d85cf23708d9875b486a76c7a3e2af250",
}

_HTML_DOC_RE = re.compile(r"<html[^>]*>.*?</html>", re.S | re.I)


def _post(fetcher: Fetcher, action: str, id_ref: str):
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}"
    body = json.dumps([id_ref], ensure_ascii=False)
    r = fetcher.rsc(ACTIONS[action], body, referer=url)
    if r.status_code != 200:
        raise RuntimeError(f"Action {action} tra ve {r.status_code}")
    return r


def fetch_doc_info(fetcher: Fetcher, id_ref: str) -> dict:
    """JSON thong tin van ban. Nam ngay sau '</html>1:' (response nhung ca HTML)."""
    text = _post(fetcher, "doc_info", id_ref).text
    marker = "</html>1:"
    idx = text.rfind(marker)
    if idx >= 0:
        start = idx + len(marker)
    else:
        idx = text.rfind('{"id":')
        if idx < 0:
            raise RuntimeError("Khong tim thay JSON doc_info")
        start = idx
    return json.loads(text[start:].strip())


def fetch_luoc_do(fetcher: Fetcher, id_ref: str) -> dict:
    """Quan he 2 chieu: {documentNamesByType, documentNamesBySource}."""
    payload = parse_rsc_payload(_post(fetcher, "luoc_do", id_ref).text, line_id="1")
    if not isinstance(payload, dict):
        return {"documentNamesByType": {}, "documentNamesBySource": {}}
    return {
        "documentNamesByType": payload.get("documentNamesByType") or {},
        "documentNamesBySource": payload.get("documentNamesBySource") or {},
    }


def fetch_lich_su(fetcher: Fetcher, id_ref: str) -> list[dict]:
    """Lifecycle + tac dong hieu luc: [{id, status, sourceDocId, title, effFrom}]."""
    payload = parse_rsc_payload(_post(fetcher, "lich_su", id_ref).text, line_id="1")
    return payload if isinstance(payload, list) else []


def fetch_vbhn(fetcher: Fetcher, id_ref: str) -> list[dict]:
    """Nhom VBHN: [{vbhnDocument, mergedDocuments: [...]}]."""
    payload = parse_rsc_payload(_post(fetcher, "vbhn", id_ref).text, line_id="1")
    return payload if isinstance(payload, list) else []


def fetch_toan_van_html(fetcher: Fetcher, id_ref: str) -> str:
    """HTML toan van sach (giua <html>...</html>)."""
    text = _post(fetcher, "toan_van", id_ref).text
    m = _HTML_DOC_RE.search(text)
    return m.group(0) if m else ""


def fetch_cay_noidung(fetcher: Fetcher, id_ref: str) -> list[dict]:
    """Cay phan cap noi dung: Chuong > Dieu > Khoan > Diem (level/children).

    Dong 1 chua cay JSON, noi dung la Dieu/Khoan/Diem duoc danh trung vao
    text-literal va tham chieu bang '$<id>'; ham tra ve cay da inline day du.
    Moi node: {key, id, title, ptype, level, orderIndex, isLeaf, content, children,
    effFrom, effTo} voi level thuoc {Chapter, Article, Clause, Point}.
    """
    chunks = parse_rsc_flight(_post(fetcher, "cay", id_ref).text)
    tree = chunks.get("1")
    if not isinstance(tree, list):
        return []
    return resolve_rsc_refs(tree, chunks)

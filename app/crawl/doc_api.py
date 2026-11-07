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
    # chi tiet 1 diem bi tac dong: body [doc_id, provision_id] -> sourceProvisions/targetProvision
    "diem_tac_dong": "2836b8008e17a31b85409db6fcd8515b307b565d",
}

_HTML_DOC_RE = re.compile(r"<html[^>]*>.*?</html>", re.S | re.I)

# <p> co ca id va type="<ma>:<source_provision_id>" -> diem bi tac dong (HTML da giai escape).
_P_TYPE_RE = re.compile(
    r'<p\b(?=[^>]*\bid="([0-9a-f-]{36})")'
    r'(?=[^>]*\btype="(\d+):([0-9a-f-]{36})")',
    re.I,
)


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


def _trich_toan_van(text: str) -> str:
    """Trich HTML toan van tu response action 'toan_van'.

    Mot so VB tra ve document <html>...</html>; nhieu VB tra RSC flight voi toan van
    nam trong text-literal (T-chunk) dang fragment <div> (khong co the <html>).
    Uu tien <html>, nguoc lai lay fragment HTML dai nhat trong cac chunk flight.
    """
    m = _HTML_DOC_RE.search(text)
    if m:
        return m.group(0)
    chunks = parse_rsc_flight(text)
    frags = [v for v in chunks.values() if isinstance(v, str) and "<" in v and ">" in v]
    return max(frags, key=len) if frags else ""


def fetch_toan_van_html(fetcher: Fetcher, id_ref: str) -> str:
    """HTML toan van (document <html> hoac fragment <div> tu RSC flight)."""
    return _trich_toan_van(_post(fetcher, "toan_van", id_ref).text)


def _unescape_rsc(html: str) -> str:
    return html.replace("\\u003c", "<").replace("\\u003e", ">").replace('\\"', '"')


def trich_diem_bi_tac_dong(html: str) -> list[tuple[str, int, str]]:
    """Parse HTML trang GET -> [(target_provision_id, ma_loai, source_provision_id)].

    Chi lay cac <p> co thuoc tinh `type` (diem bi tac dong). Diem khong co `type`
    la diem binh thuong -> bo qua. Ham thuan, test offline duoc.
    """
    html = _unescape_rsc(html)
    return [(tid, int(code), sid) for tid, code, sid in _P_TYPE_RE.findall(html)]


def fetch_diem_tac_dong(fetcher: Fetcher, id_ref: str) -> list[dict]:
    """Lay tac dong cap dieu khoan cua van ban `id_ref`.

    B1: GET trang -> tap diem bi tac dong (thuoc tinh `type`).
    B2: moi diem goi action diem_tac_dong [id_ref, diem_id] -> sourceProvisions[]
        (lenh tac dong, co the nhieu) + targetProvision (ptype/orderIndex cua diem dich).
    Tra ve danh sach CANH (1 dong / 1 source) da chuan hoa cho store.
    """
    id_ref = str(id_ref).strip()
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}?tabs=toan-van"
    targets = fetcher.get(url).text
    diems = trich_diem_bi_tac_dong(targets)

    rows: list[dict] = []
    seen: set[str] = set()
    for target_id, _code, _src in diems:
        if target_id in seen:
            continue
        seen.add(target_id)
        body = json.dumps([id_ref, target_id], ensure_ascii=False)
        r = fetcher.rsc(ACTIONS["diem_tac_dong"], body, referer=url)
        payload = parse_rsc_payload(r.text, line_id="1")
        if not isinstance(payload, dict):
            continue
        tp = payload.get("targetProvision") or {}
        for s in payload.get("sourceProvisions") or []:
            rows.append({
                "target_provision_id": target_id,
                "target_order_index": tp.get("orderIndex"),
                "source_doc_id": str(s.get("documentId")).strip() if s.get("documentId") else None,
                "source_provision_id": s.get("id"),
                "source_title": " - ".join(x for x in (s.get("title"), s.get("titleDocument")) if x),
                "ma_loai": s.get("type") if isinstance(s.get("type"), int) else _code,
                "eff_from": s.get("effFrom"),
                "eff_to": s.get("effTo"),
                "content": s.get("content"),
                "raw": s,
            })
    return rows


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

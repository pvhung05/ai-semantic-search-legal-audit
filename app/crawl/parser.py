"""Parse HTML trang chi tiet + RSC flight response.

RSC flight format: moi dong co dang "<id>:<json-ish>".
Dong 0 la mapping, cac dong 1,2,... la payload. Thuong dong 1 la payload chinh.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from app.core.html_text import html_doc_to_text

_URL_DETAIL_RE = re.compile(r"/van-ban/chi-tiet/([a-z0-9\-]+)--([A-Za-z0-9\-]+)")
_RSC_LINE_RE = re.compile(r"^(\d+):(.*)$", re.M)
_NEXT_F_RE = re.compile(r'self\.__next_f\.push\(\[1,\"(.*?)\"\]\)', re.S)
_VN_LABELS = frozenset({
    "Số hiệu", "Số ký hiệu", "Người ký", "Cơ quan ban hành", "Ngày ban hành",
    "Ngày hiệu lực", "Loại văn bản", "Lĩnh vực", "Ngành",
    "Trạng thái", "Chức danh", "Ngày ký xác thực",
    "Ngày có hiệu lực", "Ngày hết hiệu lực", "Tình trạng hiệu lực",
    "Trích yếu", "Trạng thái văn bản",
})


@dataclass
class ThuocTinhVanBan:
    url_detail: str
    id: str = ""                         # ID chuoi tu vbpl.vn (so hoac UUID)
    uuid: str | None = None
    item_id: int | None = None
    so_hieu: str | None = None
    trich_yeu: str | None = None
    tieu_de: str | None = None           # Alias cho trich_yeu
    loai: str | None = None
    co_quan: str | None = None
    nguoi_ky: str | None = None
    chuc_danh_nguoi_ky: str | None = None
    linh_vuc: str | None = None
    nganh: str | None = None
    ngay_ban_hanh: date | None = None
    ngay_hieu_luc: date | None = None
    ngay_het_hieu_luc: date | None = None
    ngay_cap_nhat_vbpl: date | None = None
    tinh_trang_raw: str | None = None
    luot_xem: int | None = None
    toan_van_text: str = ""
    rsc_data_raw: dict[str, Any] = field(default_factory=dict)


# ---------- utils ----------
def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _unescape_js_string(s: str) -> str:
    """Chunk tu __next_f.push([1,"..."]) la mot JS string literal.
    Dung json.loads voi bao ngoac kep de xu ly \\uXXXX, \\n, \\" dung chuan,
    giu nguyen ky tu Unicode da raw trong HTML UTF-8."""
    try:
        return json.loads('"' + s + '"')
    except (json.JSONDecodeError, ValueError):
        return s


# ---------- RSC flight ----------
def extract_rsc_flight_chunks(html: str) -> list[str]:
    return [_unescape_js_string(m) for m in _NEXT_F_RE.findall(html)]


def parse_rsc_payload(text: str, line_id: str = "1") -> Any:
    """Tra payload cua dong <line_id>:<json>. Mac dinh dong 1."""
    for m in _RSC_LINE_RE.finditer(text):
        if m.group(1) == line_id:
            raw = m.group(2).strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
    return None


_FLIGHT_HDR_RE = re.compile(rb"([0-9a-f]+):")
_FLIGHT_REF_RE = re.compile(r"^\$([0-9a-f]+)$")


def parse_rsc_flight(text: str) -> dict[str, Any]:
    """Boc tach TAT CA chunk cua mot RSC flight response thanh dict {id: value}.

    Khac parse_rsc_payload (chi doc theo dong): ham nay ton trong do dai khai bao
    cua text-literal 'T<hexlen>,<bytes>' nen khong bi gay boi newline raw ben trong
    chunk van ban. Can thiet cho action tra ve CAY noi dung (chuong/dieu/khoan/diem),
    noi dong 1 (JSON cay) nam ngay sau cac text-literal dai.

    - Chunk 'T<hex>,<text>'        -> gia tri la str (noi dung da giai ma UTF-8).
    - Chunk JSON ('[...]'/'{...}') -> gia tri da json.loads.
    - Con lai                      -> giu nguyen str tho.
    """
    data = text.encode("utf-8")
    n = len(data)
    chunks: dict[str, Any] = {}
    pos = 0
    while pos < n:
        m = _FLIGHT_HDR_RE.match(data, pos)
        if not m:
            nl = data.find(b"\n", pos)
            if nl < 0:
                break
            pos = nl + 1
            continue
        cid = m.group(1).decode()
        p = m.end()
        if data[p:p + 1] == b"T":  # text-literal co do dai hex (byte)
            comma = data.find(b",", p)
            length = int(data[p + 1:comma], 16)
            start = comma + 1
            chunks[cid] = data[start:start + length].decode("utf-8", "replace")
            pos = start + length
            if data[pos:pos + 1] == b"\n":
                pos += 1
        else:  # chunk JSON tren 1 dong (newline da duoc escape)
            nl = data.find(b"\n", p)
            if nl < 0:
                nl = n
            raw = data[p:nl].decode("utf-8", "replace")
            try:
                chunks[cid] = json.loads(raw)
            except json.JSONDecodeError:
                chunks[cid] = raw
            pos = nl + 1
    return chunks


def resolve_rsc_refs(value: Any, chunks: dict[str, Any]) -> Any:
    """Thay cac tham chieu '$<id>' trong value bang noi dung chunk tuong ung.

    RSC danh trung noi dung dai vao text-literal roi tham chieu lai bang chuoi
    '$2', '$1a'... Ham duyet de quy va noi lai de duoc cay day du (inline)."""
    if isinstance(value, str):
        m = _FLIGHT_REF_RE.match(value)
        if m and m.group(1) in chunks:
            return resolve_rsc_refs(chunks[m.group(1)], chunks)
        return value
    if isinstance(value, list):
        return [resolve_rsc_refs(v, chunks) for v in value]
    if isinstance(value, dict):
        return {k: resolve_rsc_refs(v, chunks) for k, v in value.items()}
    return value


# ---------- listing ----------
def parse_list_items(rsc_text: str) -> list[dict]:
    """RSC response cua action 'list' tra ve {total, pageNumber, pageSize, items}."""
    payload = parse_rsc_payload(rsc_text)
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    return items if isinstance(items, list) else []


def extract_id_from_list_item(item: dict) -> tuple[str, str | None]:
    """Tra ve (id_ref, slug). id_ref la string ID tu vbpl (so hoac UUID)."""
    id_ref = str(item.get("id") or "").strip()
    slug = None  # slug optional - URL chi can id
    return id_ref, slug


# ---------- detail ----------
_HTML_DOC_RE = re.compile(r"<html[^>]*>.*?</html>", re.S | re.I)
_DOCUMENT_MAJORS_RE = re.compile(
    r'"documentMajors"\s*:\s*(\[[^\]]*\])'
)
_MAJOR_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]+)"')


def _extract_document_majors(chunks: list[str]) -> list[str]:
    """documentMajors nam trong chunk tab Thuoc tinh, khong co id_ref.
    Lay ARRAY (co dau [) chu khong lay string label 'Lĩnh vực'."""
    out: list[str] = []
    for chunk in chunks:
        for m in _DOCUMENT_MAJORS_RE.finditer(chunk):
            arr_str = m.group(1)
            for n in _MAJOR_NAME_RE.findall(arr_str):
                if n and n not in out:
                    out.append(n)
    return out


# Thuoc tinh chi tiet nam trong chunk co 'documentMajors' (tab Thuoc tinh).
# docType la object {id, name, code}; agencyName la string truc tiep;
# documentIssues la array voi {personName, jobTitleName, agencyName}.
_DOCTYPE_OBJ_RE = re.compile(
    r'"docType"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"[^}]*?"code"\s*:\s*"([^"]+)"'
)
_AGENCY_NAME_RE = re.compile(r'"agencyName"\s*:\s*"([^"]+)"')
_PERSON_NAME_RE = re.compile(r'"personName"\s*:\s*"([^"]+)"')
_JOBTITLE_NAME_RE = re.compile(r'"jobTitleName"\s*:\s*"([^"]+)"')
_DOCFIELDS_RE = re.compile(r'"documentFields"\s*:\s*(\[[^\]]*\])')
_EXPIRY_RE = re.compile(r'"expiryDate"\s*:\s*"([^"]+)"')
_EFFECTIVE_RE = re.compile(r'"effectiveDate"\s*:\s*"([^"]+)"')
_STATUS_RE = re.compile(r'"(?:validityStatus|effectStatus)"\s*:\s*"([^"]+)"')


def _extract_thuoc_tinh_chunk_data(chunks: list[str]) -> dict[str, Any]:
    """Scan chunk 'Thuoc tinh' (chua documentMajors) de lay cac truong co cau truc:
    docType (name+code), agencyName, personName (nguoi ky), jobTitleName (chuc danh),
    documentFields (linh vuc chi tiet), expiryDate, effectiveDate, validityStatus."""
    out: dict[str, Any] = {}
    for chunk in chunks:
        if "documentMajors" not in chunk:
            continue
        if m := _DOCTYPE_OBJ_RE.search(chunk):
            out["docTypeName"] = _unescape_js_string(m.group(1))
            out["docTypeCode"] = _unescape_js_string(m.group(2))
        if m := _AGENCY_NAME_RE.search(chunk):
            out["agencyName"] = _unescape_js_string(m.group(1))
        if m := _PERSON_NAME_RE.search(chunk):
            out["personName"] = _unescape_js_string(m.group(1))
        if m := _JOBTITLE_NAME_RE.search(chunk):
            out["jobTitleName"] = _unescape_js_string(m.group(1))
        if m := _DOCFIELDS_RE.search(chunk):
            names = _MAJOR_NAME_RE.findall(m.group(1))
            if names:
                out["documentFields"] = [_unescape_js_string(n) for n in names]
        if m := _EXPIRY_RE.search(chunk):
            out["expiryDate"] = _unescape_js_string(m.group(1))
        if m := _EFFECTIVE_RE.search(chunk):
            out["effectiveDate"] = _unescape_js_string(m.group(1))
        if m := _STATUS_RE.search(chunk):
            out["validityStatus"] = _unescape_js_string(m.group(1))
        break
    return out


def _extract_full_text(chunks: list[str]) -> str:
    """Toan van la raw HTML Word embed trong mot chunk RSC flight."""
    for chunk in chunks:
        m = _HTML_DOC_RE.search(chunk)
        if m:
            return html_doc_to_text(m.group(0))
    return ""


def _collect_rsc_keys(chunks: list[str], id_ref: str | None = None) -> dict[str, str]:
    """Thu thap gia tri cho cac key. Neu truyen id_ref, chi parse chunks chua
    chuoi do."""
    out: dict[str, str] = {}
    keys = (
        "docNum", "title", "signer", "signerPosition", "issuingAgency", "docType",
        "issueDate", "effectiveDate", "expiryDate", "field", "industry",
        "validityStatus", "updatedAt", "docAbs", "documentName",
    )
    for chunk in chunks:
        if id_ref and id_ref not in chunk:
            continue
        for key in keys:
            if key in out:
                continue
            for m in re.finditer(
                r'"' + key + r'":\s*("(?:[^"\\]|\\.)*"|null)', chunk
            ):
                v = m.group(1)
                if v == "null":
                    continue
                v = _unescape_js_string(v[1:-1])
                if v in _VN_LABELS:
                    continue
                out[key] = v
                break
    return out


def parse_detail_html(html: str, url: str, id_ref: str) -> ThuocTinhVanBan:
    soup = BeautifulSoup(html, "lxml")

    is_uuid = "-" in id_ref and not id_ref.isdigit()
    tt = ThuocTinhVanBan(
        url_detail=url,
        id=id_ref,
        uuid=id_ref if is_uuid else None,
        item_id=int(id_ref) if id_ref.isdigit() else None,
    )

    h1 = soup.select_one("h1")
    if h1:
        tt.trich_yeu = h1.get_text(" ", strip=True) or None

    labels = soup.select("[class*='_dateLabel__']")
    values = soup.select("[class*='_dateValue__']")
    for lab, val in zip(labels, values):
        key = lab.get_text(" ", strip=True).rstrip(":").lower()
        v = val.get_text(" ", strip=True)
        if "cập nhật" in key:
            tt.ngay_cap_nhat_vbpl = _parse_date(v)
        elif "hiệu lực" in key:
            tt.ngay_hieu_luc = _parse_date(v)

    chunks = extract_rsc_flight_chunks(html)
    rsc_data = _collect_rsc_keys(chunks, id_ref=id_ref)
    tt.rsc_data_raw = rsc_data

    for sel in ("script", "style", "nav", "header", "footer",
                "[class*='ida_modal']", "[class*='cookie']", "[class*='Header_']",
                "[class*='Footer_']"):
        for el in soup.select(sel):
            el.decompose()

    status_el = soup.find(string=re.compile(
        r"(Hết hiệu lực|Còn hiệu lực|Ngưng hiệu lực|Chưa có hiệu lực)", re.I
    ))
    if status_el:
        tt.tinh_trang_raw = status_el.strip()

    body_text_for_views = soup.body.get_text(" ", strip=True) if soup.body else ""
    m = re.search(r"([\d\.]+)\s*lượt xem", body_text_for_views)
    if m:
        tt.luot_xem = int(m.group(1).replace(".", ""))

    tt.so_hieu = rsc_data.get("docNum") or tt.so_hieu
    if not tt.trich_yeu:
        tt.trich_yeu = rsc_data.get("title") or rsc_data.get("documentName")
    tt.tieu_de = tt.trich_yeu

    # Thuoc tinh chi tiet tu chunk 'Thuoc tinh' (chua documentMajors)
    thuoc_tinh = _extract_thuoc_tinh_chunk_data(chunks)
    tt.rsc_data_raw.update({"_thuoc_tinh": thuoc_tinh})

    tt.nguoi_ky = thuoc_tinh.get("personName") or rsc_data.get("signer")
    tt.chuc_danh_nguoi_ky = thuoc_tinh.get("jobTitleName") or rsc_data.get("signerPosition")
    tt.co_quan = thuoc_tinh.get("agencyName") or rsc_data.get("issuingAgency")
    tt.loai = thuoc_tinh.get("docTypeName") or rsc_data.get("docType")
    tt.nganh = rsc_data.get("industry")

    majors = _extract_document_majors(chunks)
    tt.linh_vuc = majors[0] if majors else rsc_data.get("field")

    tt.ngay_ban_hanh = _parse_date(rsc_data.get("issueDate"))
    if not tt.ngay_hieu_luc:
        tt.ngay_hieu_luc = _parse_date(
            thuoc_tinh.get("effectiveDate") or rsc_data.get("effectiveDate")
        )
    tt.ngay_het_hieu_luc = _parse_date(
        thuoc_tinh.get("expiryDate") or rsc_data.get("expiryDate")
    )
    if not tt.tinh_trang_raw and thuoc_tinh.get("validityStatus"):
        tt.tinh_trang_raw = thuoc_tinh["validityStatus"]

    tt.toan_van_text = _extract_full_text(chunks)
    return tt


# ---------- quan he (lien quan - full 2 chieu) ----------
def parse_lien_quan(rsc_text: str) -> dict[str, dict[str, list[dict]]]:
    """Parse RSC payload cua action 'lien_quan' (lược đồ FULL 2 chiều).
    Tra ve dict:
      {
        "documentNamesByType": { "<ma>": [ {id, name, effectAllType}, ... ] },
        "documentNamesBySource": { "<ma>": [ {id, name, effectAllType}, ... ] }
      }
    """
    payload = parse_rsc_payload(rsc_text)
    if not isinstance(payload, dict):
        return {"documentNamesByType": {}, "documentNamesBySource": {}}
    by_type = payload.get("documentNamesByType")
    by_source = payload.get("documentNamesBySource")
    return {
        "documentNamesByType": by_type if isinstance(by_type, dict) else {},
        "documentNamesBySource": by_source if isinstance(by_source, dict) else {},
    }


# ---------- quan he (luoc do - tac dong hieu luc + lifecycle) ----------
def parse_luoc_do(rsc_text: str) -> list[dict]:
    """Tra ve list quan he {id, status, sourceDocId, title, effFrom}."""
    payload = parse_rsc_payload(rsc_text)
    if not isinstance(payload, list):
        return []
    return [x for x in payload if isinstance(x, dict)]


# ---------- van ban hop nhat (vbhn) ----------
def parse_vbhn(rsc_text: str) -> list[dict]:
    """Parse RSC payload cua action 'vbhn'.
    Tra ve list cac nhom VBHN:
      [ { "vbhnDocument": {...}, "mergedDocuments": [...] }, ... ]
    """
    payload = parse_rsc_payload(rsc_text)
    if not isinstance(payload, list):
        return []
    return [x for x in payload if isinstance(x, dict)]


# ---------- discover ----------
def extract_ids_from_html(html: str) -> list[tuple[str, str]]:
    """Khi can discover tu HTML (vd homepage): tra (slug, id_ref) duy nhat."""
    out, seen = [], set()
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select("a[href]"):
        m = _URL_DETAIL_RE.search(a.get("href", ""))
        if not m:
            continue
        slug, id_ref = m.group(1), m.group(2)
        if id_ref in seen:
            continue
        seen.add(id_ref)
        out.append((slug, id_ref))
    return out

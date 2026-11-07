"""Dieu phoi: discover -> crawl mot van ban tu vbpl.vn vao schema meta.

Crawl dung 5 API JSON/HTML sach qua doc_api:
  doc_info  -> metadata (documents + nganh + linhvuc + issues + tep_dinh_kem)
  toan_van  -> noi dung (document_content)
  luoc_do   -> quan he 2 chieu (document_relations)
  lich_su   -> lifecycle (ngay ban hanh/hieu luc) + ngay tac dong
  vbhn      -> van ban hop nhat (vbhn_nhom)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

import psycopg

from . import doc_api, parser, store
from .fetcher import BASE, Fetcher

# vbpl chan phan trang sau ~6500 (lat tiep tra rong du total ~57k). Khoang ngay nao co
# total > nguong nay -> tu chia doi de moi mang lat het duoc.
NGUONG_TRAN = 6000

log = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    id_ref: str
    so_hieu: str | None
    tieu_de: str | None
    trangthai: str | None
    quan_he_count: int
    noidung_len: int


def discover_from_list(conn: psycopg.Connection, fetcher: Fetcher,
                       page: int = 1, page_size: int = 100,
                       issue_from: str | None = None, issue_to: str | None = None) -> int:
    """Goi action 'list' lay 1 trang danh sach van ban TW -> enqueue.

    issue_from/issue_to: loc theo ngay ban hanh (chuoi truyen thang xuong filter vbpl) de
    chia nho truy vat, VUOT TRAN phan trang ~6500 cua vbpl (tong that ~57k). Format can
    kiem chung voi API that (thu 'dd/mm/yyyy' hoac ISO) - xem log total doi khong.
    """
    action = store.get_action_id(conn, "list")
    body = json.dumps([{
        "pageNumber": page, "pageSize": page_size, "keyword": "$undefined",
        "sortBy": "issueDate", "sortDirection": "desc", "groupVbpl": False,
        "documentName": "$undefined", "docNum": "$undefined", "docType": "$undefined",
        "majorTypeIds": "$undefined", "fieldTypeIds": "$undefined",
        "agencyIds": "$undefined", "effStatus": "$undefined", "status": "$undefined",
        "issueDateFrom": issue_from or "$undefined", "issueDateTo": issue_to or "$undefined",
        "administrativeUnit": "$undefined", "agencyLevel": "TRUNG_UONG",
        "documentType": "$undefined", "optionDoc": "all", "matchMode": "all_words",
    }], ensure_ascii=False)
    r = fetcher.rsc(action, body, referer=BASE + "/van-ban/trung-uong")
    store.save_raw(conn, f"list_p{page}", "rsc_list", r.text, r.status_code)
    items = parser.parse_list_items(r.text)
    total = parser.parse_list_total(r.text)
    added = 0
    for it in items:
        id_ref, slug = parser.extract_id_from_list_item(it)
        if id_ref and store.enqueue(conn, id_ref, slug):
            added += 1
    conn.commit()
    log.info("discover page %d: %d items, %d moi (vbpl bao total=%s)",
             page, len(items), added, total)
    return len(items), total   # (so item trang; tong vbpl bao). 0 item = het danh sach.


def _iso(d: date) -> str:
    """Format ngay cho filter issueDate cua vbpl (vd '2023-01-01T00:00:00')."""
    return d.strftime("%Y-%m-%dT00:00:00")


def discover_khoang(conn: psycopg.Connection, fetcher: Fetcher,
                    d1: date, d2: date, page_size: int = 100) -> None:
    """Enqueue moi VB co ngay ban hanh trong [d1, d2]. Neu total > NGUONG_TRAN va con chia
    duoc -> tach doi khoang (de qui) cho tung mang lat het, vuot tran phan trang cua vbpl."""
    page = 1
    while True:
        n_items, total = discover_from_list(conn, fetcher, page, page_size,
                                            issue_from=_iso(d1), issue_to=_iso(d2))
        if page == 1 and total and total > NGUONG_TRAN and d1 < d2:
            mid = d1 + (d2 - d1) // 2
            log.info("discover khoang %s..%s total=%d > %d -> chia doi tai %s",
                     d1, d2, total, NGUONG_TRAN, mid)
            discover_khoang(conn, fetcher, d1, mid, page_size)
            discover_khoang(conn, fetcher, mid + timedelta(days=1), d2, page_size)
            return
        if n_items == 0:
            return
        page += 1


def crawl_one(conn: psycopg.Connection, fetcher: Fetcher,
              id_ref: str, slug: str | None = None,
              enqueue_related: bool = True) -> CrawlResult:
    """enqueue_related=False: chi cao 66801, khong dua van ban lien quan vao queue
    (van tao stub de giu FK luoc do)."""
    id_ref = str(id_ref).strip()
    url = f"{BASE}/van-ban/chi-tiet/{slug or 'x'}--{id_ref}"

    info = doc_api.fetch_doc_info(fetcher, id_ref)
    toan_van_html = doc_api.fetch_toan_van_html(fetcher, id_ref)
    luoc_do = doc_api.fetch_luoc_do(fetcher, id_ref)
    lich_su = doc_api.fetch_lich_su(fetcher, id_ref)
    vbhn = doc_api.fetch_vbhn(fetcher, id_ref)

    store.save_raw(conn, id_ref, "doc_info", json.dumps(info, ensure_ascii=False), 200)
    store.save_raw(conn, id_ref, "toan_van", toan_van_html, 200)

    store.upsert_document(conn, info, toan_van_html, nguon_url=url)
    rel_count = store.save_relations(conn, id_ref, luoc_do, lich_su,
                                     enqueue_related=enqueue_related)
    store.apply_lifecycle(conn, id_ref, lich_su)
    store.save_vbhn(conn, vbhn, enqueue_related=enqueue_related)
    conn.commit()

    return CrawlResult(
        id_ref=id_ref, so_hieu=info.get("docNum"), tieu_de=info.get("title"),
        trangthai=(info.get("effStatus") or {}).get("name"),
        quan_he_count=rel_count,
        noidung_len=len(parser.html_doc_to_text(toan_van_html)),
    )

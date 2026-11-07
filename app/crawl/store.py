"""Luu du lieu crawl vao Postgres schema `meta`.

Nguon metadata: JSON tu doc_api (doc_info, luoc_do, lich_su, vbhn) + HTML toan_van.
Khoa chinh documents.id la id goc tu vbpl.vn (chuoi).
"""
from __future__ import annotations

import json
import logging
import re
import zlib
from datetime import date, datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

from . import parser
from .actions import DEFAULT_ACTIONS

log = logging.getLogger(__name__)

# Cot document_content.tsv = GENERATED to_tsvector(noidung). VBHN hop nhat co noidung nhieu MB
# -> to_tsvector ngon RAM -> Postgres OOM/dong ket noi. Cat phan tsvector o day; full van o
# noidung_html + raw_html. shortcut: 1M ky tu du cho FTS; nang len neu can.
_NOIDUNG_MAX = 1_000_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(s: str | None) -> date | None:
    """ISO '2014-12-22T00:00:00' hoac 'dd/mm/yyyy' -> date."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _slugify(text: str, max_len: int = 50) -> str:
    s = re.sub(r"[^\w\s-]", "", text.strip())
    s = re.sub(r"[\s_-]+", "_", s)
    return s.upper()[:max_len]


# ---------- action_config ----------
def seed_actions(conn: psycopg.Connection) -> int:
    n = 0
    with conn.cursor() as cur:
        for a in DEFAULT_ACTIONS:
            cur.execute(
                "INSERT INTO vanban.action_config(ten, action_id, body_mau, ghi_chu, updated_at) "
                "VALUES (%s, %s, %s, %s, now()) "
                "ON CONFLICT (ten) DO UPDATE SET action_id = EXCLUDED.action_id, "
                "body_mau = EXCLUDED.body_mau, ghi_chu = EXCLUDED.ghi_chu, updated_at = now()",
                (a.ten, a.action_id, Jsonb(json.loads(a.body_mau)), a.ghi_chu),
            )
            n += cur.rowcount
    return n


def get_action_id(conn: psycopg.Connection, ten: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT action_id FROM vanban.action_config WHERE ten = %s", (ten,))
        row = cur.fetchone()
    if row:
        return row[0]
    for a in DEFAULT_ACTIONS:
        if a.ten == ten:
            return a.action_id
    raise LookupError(f"Khong co action '{ten}'")


# ---------- raw html ----------
def save_raw(conn: psycopg.Connection, id_ref: str, loai_trang: str,
             text: str, http_status: int) -> None:
    blob = zlib.compress(text.encode("utf-8"))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO vanban.raw_html(id_ref, loai_trang, html, fetched_at, http_status) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (id_ref, loai_trang) DO UPDATE SET html = EXCLUDED.html, "
            "fetched_at = EXCLUDED.fetched_at, http_status = EXCLUDED.http_status",
            (id_ref, loai_trang, blob, _now(), http_status),
        )


# ---------- catalog ----------
def _get_or_create_catalog(
    cur: psycopg.Cursor, table: str, vbpl_id: str | None,
    ma: str | None, ten: str | None, extra: dict | None = None,
) -> int | None:
    """Lookup theo vbpl_id -> ma -> ten; tao moi neu thieu. Tra ve id."""
    if not ten or not ten.strip():
        return None
    ten = ten.strip()
    vbpl_id = (str(vbpl_id).strip() or None) if vbpl_id else None
    ma = (ma.strip() or None) if ma else None

    if vbpl_id:
        cur.execute(f"SELECT id FROM danhmuc.{table} WHERE vbpl_id = %s", (vbpl_id,))
        if r := cur.fetchone():
            return r[0]
    if ma:
        cur.execute(f"SELECT id FROM danhmuc.{table} WHERE ma = %s", (ma,))
        if r := cur.fetchone():
            return r[0]
    cur.execute(f"SELECT id FROM danhmuc.{table} WHERE ten = %s LIMIT 1", (ten,))
    if r := cur.fetchone():
        return r[0]

    if not ma:
        ma = (vbpl_id or _slugify(ten))[:50]
    cols = ["vbpl_id", "ma", "ten"]
    vals = [vbpl_id, ma, ten]
    for k, v in (extra or {}).items():
        cols.append(k)
        vals.append(v)
    ph = ", ".join(["%s"] * len(cols))
    cur.execute(
        f"INSERT INTO danhmuc.{table}({', '.join(cols)}) VALUES ({ph}) "
        f"ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten, "
        f"vbpl_id = COALESCE(EXCLUDED.vbpl_id, danhmuc.{table}.vbpl_id) RETURNING id",
        tuple(vals),
    )
    return cur.fetchone()[0]


_EFFSTATUS_MAP = {
    "CHL": "CON_HIEU_LUC",
    "HHL": "HET_HIEU_LUC",
    "HHLMP": "HET_HIEU_LUC_MOT_PHAN",
    "NHL": "TAM_NGUNG",
    "CCHL": "CHUA_HIEU_LUC",
}


def _map_trangthai(eff_code: str | None, eff_name: str | None) -> str:
    if eff_code and eff_code.upper() in _EFFSTATUS_MAP:
        return _EFFSTATUS_MAP[eff_code.upper()]
    low = (eff_name or "").lower()
    if "một phần" in low:
        return "HET_HIEU_LUC_MOT_PHAN"
    if "hết hiệu lực" in low:
        return "HET_HIEU_LUC"
    if "còn hiệu lực" in low:
        return "CON_HIEU_LUC"
    if "ngưng" in low:
        return "TAM_NGUNG"
    if "chưa" in low:
        return "CHUA_HIEU_LUC"
    return "KHONG_XAC_DINH"


# ---------- documents ----------
def ensure_stub(cur: psycopg.Cursor, doc_id: str, tieu_de: str | None = None,
                so_hieu: str | None = None, enqueue_it: bool = True) -> None:
    """Dam bao van ban lien quan ton tai (de thoa man FK) + enqueue de crawl sau."""
    doc_id = str(doc_id).strip()
    if not doc_id:
        return
    cur.execute("SELECT 1 FROM vanban.documents WHERE id = %s", (doc_id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO vanban.documents(id, so_hieu, tieu_de) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (doc_id, so_hieu, (tieu_de or f"[vbpl:{doc_id}]").strip()),
        )
    if enqueue_it:
        cur.execute(
            "INSERT INTO vanban.crawl_queue(id_ref) VALUES (%s) ON CONFLICT (id_ref) DO NOTHING",
            (doc_id,),
        )


def upsert_document(conn: psycopg.Connection, info: dict, toan_van_html: str = "",
                    nguon_url: str | None = None) -> str:
    """Upsert metadata van ban tu JSON doc_info + HTML toan van."""
    doc_id = str(info["id"]).strip()
    with conn.cursor() as cur:
        # Danh muc
        dt = info.get("docType") or {}
        loai_id = _get_or_create_catalog(
            cur, "loai_vanban", dt.get("id"), dt.get("code"), dt.get("name"),
            extra={"nhom": dt.get("parentCode")},
        )
        org = info.get("organization") or {}
        coquan_id = _get_or_create_catalog(
            cur, "coquan_banhanh", org.get("id"), org.get("code"),
            org.get("name") or info.get("agencyName"),
            extra={"ten_en": org.get("nameEn")},
        )

        # Nguoi ky dau tien (tien loi)
        issues = info.get("documentIssues") or []
        primary = issues[0] if issues else {}
        chucdanh_id = _get_or_create_catalog(
            cur, "chucdanh", primary.get("jobTitleId"),
            primary.get("jobTitleCode"), primary.get("jobTitleName"),
        )
        nguoi_ky = primary.get("personName")

        # Nganh dau tien
        majors = info.get("documentMajors") or []
        nganh_id = None
        if majors:
            nganh_id = _get_or_create_catalog(
                cur, "nganh", majors[0].get("id"), majors[0].get("code"), majors[0].get("name"),
            )

        trangthai = _map_trangthai(
            (info.get("effStatus") or {}).get("code"),
            (info.get("effStatus") or {}).get("name"),
        )

        cur.execute(
            """
            INSERT INTO vanban.documents (
                id, so_hieu, tieu_de, loai_vanban_id, coquan_id, nganh_id, chucdanh_id,
                nguoi_ky, docgroup, ngay_banhanh, ngay_hieuluc, ngay_hethieuluc, ngay_congbo,
                trangthai, effstatus_code, ghi_chu_apdung, lang,
                is_consolidated, vbpl_updated_date, nguon_url, created_at, updated_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,
                %s::vanban.trangthai_hieuluc,%s,%s,%s, %s,%s,%s, now(), now()
            )
            ON CONFLICT (id) DO UPDATE SET
                so_hieu = EXCLUDED.so_hieu, tieu_de = EXCLUDED.tieu_de,
                loai_vanban_id = COALESCE(EXCLUDED.loai_vanban_id, vanban.documents.loai_vanban_id),
                coquan_id = COALESCE(EXCLUDED.coquan_id, vanban.documents.coquan_id),
                nganh_id = COALESCE(EXCLUDED.nganh_id, vanban.documents.nganh_id),
                chucdanh_id = COALESCE(EXCLUDED.chucdanh_id, vanban.documents.chucdanh_id),
                nguoi_ky = EXCLUDED.nguoi_ky, docgroup = EXCLUDED.docgroup,
                ngay_banhanh = EXCLUDED.ngay_banhanh, ngay_hieuluc = EXCLUDED.ngay_hieuluc,
                ngay_hethieuluc = EXCLUDED.ngay_hethieuluc, ngay_congbo = EXCLUDED.ngay_congbo,
                trangthai = EXCLUDED.trangthai, effstatus_code = EXCLUDED.effstatus_code,
                ghi_chu_apdung = EXCLUDED.ghi_chu_apdung, lang = EXCLUDED.lang,
                is_consolidated = EXCLUDED.is_consolidated,
                vbpl_updated_date = EXCLUDED.vbpl_updated_date, nguon_url = EXCLUDED.nguon_url,
                updated_at = now()
            """,
            (
                doc_id, info.get("docNum"), info.get("title") or f"[vbpl:{doc_id}]",
                loai_id, coquan_id, nganh_id, chucdanh_id,
                nguoi_ky, info.get("docGroup"),
                _parse_dt(info.get("issueDate")), _parse_dt(info.get("effFrom")),
                _parse_dt(info.get("effTo")), _parse_dt(info.get("publicDate")),
                trangthai, (info.get("effStatus") or {}).get("code"),
                info.get("applicationNote"), info.get("lang"),
                bool(info.get("isConsolidatedDocument")),
                _parse_dt(info.get("updatedDate")), nguon_url,
            ),
        )

        # document_nganh (tat ca)
        for mj in majors:
            nid = _get_or_create_catalog(cur, "nganh", mj.get("id"), mj.get("code"), mj.get("name"))
            if nid:
                cur.execute(
                    "INSERT INTO vanban.document_nganh(document_id, nganh_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING", (doc_id, nid),
                )

        # document_linhvuc (documentFields)
        for fld in info.get("documentFields") or []:
            lid = _get_or_create_catalog(cur, "linhvuc", fld.get("id"), fld.get("code"), fld.get("name"))
            if lid:
                cur.execute(
                    "INSERT INTO vanban.document_linhvuc(document_id, linhvuc_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING", (doc_id, lid),
                )

        # document_issues (tat ca nguoi ky)
        cur.execute("DELETE FROM vanban.document_issues WHERE document_id = %s", (doc_id,))
        for iss in issues:
            cq = _get_or_create_catalog(
                cur, "coquan_banhanh", iss.get("agencyId"), iss.get("agencyCode"),
                iss.get("agencyName"), extra={"ten_en": iss.get("agencyNameEn")},
            )
            cd = _get_or_create_catalog(
                cur, "chucdanh", iss.get("jobTitleId"), iss.get("jobTitleCode"), iss.get("jobTitleName"),
            )
            cur.execute(
                "INSERT INTO vanban.document_issues(document_id, coquan_id, chucdanh_id, nguoi_ky, thu_tu) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (doc_id, cq, cd, iss.get("personName"), iss.get("orderIndex")),
            )

        # Toan van
        if toan_van_html:
            noidung = parser.html_doc_to_text(toan_van_html)
            if len(noidung) > _NOIDUNG_MAX:
                log.warning("doc %s noidung %d ky tu -> cat con %d (tranh OOM tsvector)",
                            doc_id, len(noidung), _NOIDUNG_MAX)
                noidung = noidung[:_NOIDUNG_MAX]
            cur.execute(
                "INSERT INTO vanban.document_content(document_id, noidung, noidung_html, file_path, updated_at) "
                "VALUES (%s, %s, %s, %s, now()) "
                "ON CONFLICT (document_id) DO UPDATE SET noidung = EXCLUDED.noidung, "
                "noidung_html = EXCLUDED.noidung_html, file_path = EXCLUDED.file_path, "
                "version = vanban.document_content.version + 1, updated_at = now()",
                (doc_id, noidung, toan_van_html, info.get("documentContentFileName")),
            )
    return doc_id


# ---------- quan he (luoc_do + lich_su) ----------
def _rel_type_id_cache(cur: psycopg.Cursor) -> dict[str, int]:
    cur.execute("SELECT vbpl_code, id FROM danhmuc.relation_types WHERE vbpl_code IS NOT NULL")
    return {code: rid for code, rid in cur.fetchall()}


def _lich_su_index(lich_su: list[dict]) -> dict[str, dict]:
    """Map sourceDocId -> item (de lay effFrom cho quan he)."""
    out: dict[str, dict] = {}
    for it in lich_su:
        src = str(it.get("sourceDocId") or "").strip()
        if src:
            out[src] = it
    return out


def save_relations(conn: psycopg.Connection, doc_id: str,
                   luoc_do: dict, lich_su: list[dict],
                   enqueue_related: bool = True) -> int:
    """Luu quan he 2 chieu tu luoc_do; bo sung ngay_hieuluc tu lich_su.
    byType:   doc_id TAC DONG -> item BI TAC DONG.
    bySource: item TAC DONG   -> doc_id BI TAC DONG.
    enqueue_related=False: tao stub van ban dich nhung KHONG dua vao crawl_queue.
    """
    doc_id = str(doc_id).strip()
    by_type = luoc_do.get("documentNamesByType") or {}
    by_source = luoc_do.get("documentNamesBySource") or {}
    ls_idx = _lich_su_index(lich_su)
    n = 0
    with conn.cursor() as cur:
        rel_ids = _rel_type_id_cache(cur)
        cur.execute(
            "DELETE FROM vanban.document_relations "
            "WHERE vanban_tacdong_id = %s OR vanban_bitacdong_id = %s",
            (doc_id, doc_id),
        )
        # byType: doc_id tac dong -> item bi tac dong
        for code, items in by_type.items():
            n += _insert_rels(cur, rel_ids, ls_idx, code, items, doc_id,
                              doc_is_tacdong=True, enqueue_related=enqueue_related)
        # bySource: item tac dong -> doc_id bi tac dong
        for code, items in by_source.items():
            n += _insert_rels(cur, rel_ids, ls_idx, code, items, doc_id,
                              doc_is_tacdong=False, enqueue_related=enqueue_related)
    return n


def _insert_rels(cur, rel_ids, ls_idx, code, items, doc_id, doc_is_tacdong,
                 enqueue_related=True) -> int:
    rid = rel_ids.get(str(code))
    if rid is None or not items:
        return 0
    n = 0
    for it in items:
        other = str(it.get("id") or "").strip()
        if not other:
            continue
        ensure_stub(cur, other, it.get("name"), enqueue_it=enqueue_related)
        a = doc_id if doc_is_tacdong else other   # vanban_tacdong_id
        b = other if doc_is_tacdong else doc_id    # vanban_bitacdong_id
        if not a or not b or a == b:
            continue
        ls = ls_idx.get(other, {})
        cur.execute(
            "INSERT INTO vanban.document_relations"
            "(vanban_tacdong_id, vanban_bitacdong_id, relation_type_id, effect_all_type, "
            " ghi_chu, ngay_hieuluc) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (a, b, rid, it.get("effectAllType"), it.get("name"),
             _parse_dt(ls.get("effFrom"))),
        )
        n += cur.rowcount
    return n


# ---------- tac dong cap dieu khoan (provision-level) ----------
def save_provision_impacts(conn: psycopg.Connection, doc_id: str,
                           impacts: list[dict], enqueue_related: bool = True) -> int:
    """Luu vanban.provision_impacts cho van ban doc_id (bi tac dong).

    Lam moi: DELETE theo target_doc_id roi INSERT lai (giong save_relations).
    `impacts` = output doc_api.fetch_diem_tac_dong (moi phan tu 1 canh).
    Bo qua canh co ma_loai khong co trong relation_types (vbpl_code).
    """
    doc_id = str(doc_id).strip()
    n = 0
    with conn.cursor() as cur:
        rel_ids = _rel_type_id_cache(cur)  # vbpl_code (str) -> relation_type_id
        cur.execute("DELETE FROM vanban.provision_impacts WHERE target_doc_id = %s", (doc_id,))
        for im in impacts:
            rid = rel_ids.get(str(im.get("ma_loai")))
            if rid is None:
                log.warning("ma loai %s khong co trong relation_types, bo canh", im.get("ma_loai"))
                continue
            src_doc = im.get("source_doc_id")
            if src_doc:
                ensure_stub(cur, src_doc, im.get("source_title"), enqueue_it=enqueue_related)
            cur.execute(
                """INSERT INTO vanban.provision_impacts
                     (target_doc_id, target_provision_id, target_order_index,
                      source_doc_id, source_provision_id, source_title,
                      relation_type_id, eff_from, eff_to, content, raw)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (target_provision_id, source_provision_id, relation_type_id, eff_from)
                   DO NOTHING""",
                (doc_id, im["target_provision_id"], im.get("target_order_index"),
                 src_doc, im.get("source_provision_id"), im.get("source_title"),
                 rid, _parse_dt(im.get("eff_from")), _parse_dt(im.get("eff_to")),
                 im.get("content"), Jsonb(im.get("raw"))),
            )
            n += cur.rowcount
    return n


# ---------- lifecycle tu lich_su ----------
def apply_lifecycle(conn: psycopg.Connection, doc_id: str, lich_su: list[dict]) -> None:
    """Bo sung ngay_banhanh / ngay_hieuluc tu cac item lifecycle (sourceDocId null)."""
    ban_hanh = hieu_luc = None
    for it in lich_su:
        if it.get("sourceDocId"):
            continue
        status = (it.get("status") or "").lower()
        eff = _parse_dt(it.get("effFrom"))
        if "ban hành" in status:
            ban_hanh = eff
        elif "hiệu lực" in status:
            hieu_luc = eff
    if ban_hanh or hieu_luc:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vanban.documents SET ngay_banhanh = COALESCE(ngay_banhanh, %s), "
                "ngay_hieuluc = COALESCE(ngay_hieuluc, %s) WHERE id = %s",
                (ban_hanh, hieu_luc, doc_id),
            )


# ---------- VBHN ----------
def save_vbhn(conn: psycopg.Connection, vbhn: list[dict],
              enqueue_related: bool = True) -> int:
    n = 0
    with conn.cursor() as cur:
        for group in vbhn:
            v = group.get("vbhnDocument") or {}
            vbhn_id = str(v.get("id") or "").strip()
            if not vbhn_id:
                continue
            ensure_stub(cur, vbhn_id, v.get("title"), v.get("docNum"), enqueue_it=enqueue_related)
            for m in group.get("mergedDocuments") or []:
                mid = str(m.get("id") or "").strip()
                if not mid:
                    continue
                ensure_stub(cur, mid, m.get("title"), m.get("docNum"), enqueue_it=enqueue_related)
                cur.execute(
                    "INSERT INTO vanban.vbhn_nhom(vbhn_id, thanhvien_id, la_hien_tai) "
                    "VALUES (%s, %s, %s) ON CONFLICT (vbhn_id, thanhvien_id) "
                    "DO UPDATE SET la_hien_tai = EXCLUDED.la_hien_tai",
                    (vbhn_id, mid, bool(m.get("current"))),
                )
                n += 1
    return n


# ---------- crawl queue ----------
def enqueue(conn: psycopg.Connection, id_ref: str, slug: str | None = None) -> bool:
    id_ref = str(id_ref).strip()
    if not id_ref:
        return False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO vanban.crawl_queue(id_ref, slug) VALUES (%s, %s) "
            "ON CONFLICT (id_ref) DO NOTHING", (id_ref, slug),
        )
        return cur.rowcount > 0


def take_pending(conn: psycopg.Connection, limit: int,
                 max_retry: int = 3) -> list[tuple[str, str | None]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id_ref, slug FROM vanban.crawl_queue "
            "WHERE trang_thai IN ('PENDING','ERROR') AND so_lan_thu < %s "
            "ORDER BY created_at ASC LIMIT %s", (max_retry, limit),
        )
        return [(str(r[0]), r[1]) for r in cur.fetchall()]


def mark_done(conn: psycopg.Connection, id_ref: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE vanban.crawl_queue SET trang_thai='DONE', cap_nhat=%s, loi=NULL "
            "WHERE id_ref = %s", (_now(), str(id_ref).strip()),
        )


def mark_error(conn: psycopg.Connection, id_ref: str, err: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE vanban.crawl_queue SET trang_thai='ERROR', so_lan_thu = so_lan_thu + 1, "
            "loi = %s, cap_nhat = %s WHERE id_ref = %s",
            (err[:1000], _now(), str(id_ref).strip()),
        )

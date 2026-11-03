"""Nap danh muc chuan tu vbpl.vn vao meta.loai_vanban, meta.coquan_banhanh, meta.linhvuc.

Dung 2 Server Action:
  'danh_muc' (groupCode = LoaiVanBan | LinhVuc)
  'co_quan'  (type = 'TW')
"""
from __future__ import annotations

import json
import logging
import re

import psycopg

from . import parser, store
from .fetcher import BASE, Fetcher

log = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.strip())
    s = re.sub(r"[\s_-]+", "_", s)
    return s.upper()[:30]


def _rsc_list_items(fetcher: Fetcher, action_id: str, body_obj: dict) -> list[dict]:
    body = json.dumps([body_obj], ensure_ascii=False)
    r = fetcher.rsc(action_id, body, referer=BASE + "/van-ban/trung-uong")
    payload = parser.parse_rsc_payload(r.text)
    if isinstance(payload, dict):
        items = payload.get("items", [])
        return items if isinstance(items, list) else []
    return []


def seed_loai_van_ban(conn: psycopg.Connection, fetcher: Fetcher) -> int:
    action = store.get_action_id(conn, "danh_muc")
    items = _rsc_list_items(fetcher, action, {
        "groupCode": "LoaiVanBan",
        "keyword": "$undefined",
        "includeInactive": True,
    })
    n = 0
    with conn.cursor() as cur:
        for it in items:
            ma = (it.get("code") or _slugify(it.get("name") or "")).strip()
            ten = (it.get("name") or "").strip()
            if not ma or not ten:
                continue
            cur.execute(
                "INSERT INTO meta.loai_vanban(ma, ten, mo_ta) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten",
                (ma[:30], ten[:100], it.get("shortName")),
            )
            n += 1
    return n


def seed_linh_vuc(conn: psycopg.Connection, fetcher: Fetcher) -> int:
    action = store.get_action_id(conn, "danh_muc")
    items = _rsc_list_items(fetcher, action, {
        "groupCode": "LinhVuc",
        "keyword": "$undefined",
        "includeInactive": True,
    })
    n = 0
    with conn.cursor() as cur:
        for it in items:
            ma = (it.get("code") or _slugify(it.get("name") or "")).strip()
            ten = (it.get("name") or "").strip()
            if not ma or not ten:
                continue
            cur.execute(
                "INSERT INTO meta.linhvuc(ma, ten, mo_ta) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten",
                (ma[:50], ten[:255], it.get("nameEn")),
            )
            n += 1
    return n


def seed_co_quan(conn: psycopg.Connection, fetcher: Fetcher) -> int:
    action = store.get_action_id(conn, "co_quan")
    items = _rsc_list_items(fetcher, action, {
        "keyword": "$undefined",
        "type": "TW",
        "administrativeUnitId": "$undefined",
        "includeInactive": True,
    })
    n = 0
    with conn.cursor() as cur:
        for it in items:
            ma = (it.get("code") or _slugify(it.get("name") or "")).strip()
            ten = (it.get("name") or "").strip()
            if not ma or not ten:
                continue
            cur.execute(
                "INSERT INTO meta.coquan_banhanh(ma, ten, mo_ta) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten",
                (ma[:50], ten[:255], it.get("agencyLevel")),
            )
            n += 1
    return n


def seed_all(conn: psycopg.Connection, fetcher: Fetcher) -> dict[str, int]:
    out = {
        "loai_vanban": seed_loai_van_ban(conn, fetcher),
        "linhvuc": seed_linh_vuc(conn, fetcher),
        "coquan_banhanh": seed_co_quan(conn, fetcher),
    }
    conn.commit()
    return out

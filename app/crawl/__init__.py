"""Crawler vbpl.vn: Next.js App Router + Server Actions.

Luong hoat dong:
  seed_actions()       seed cac Server Action ID vao meta.action_config
  discover()           duyet list theo phan trang (action 'list'), enqueue vao meta.crawl_queue
  crawl_one(id_ref)    GET detail HTML + POST lien_quan + POST luoc_do + POST vbhn
                       -> upsert vao meta.documents, meta.document_content, meta.document_relations
  seed_catalogs()      goi action danh_muc & co_quan -> seed meta.loai_vanban, meta.coquan_banhanh, meta.linhvuc
"""
from .fetcher import Fetcher
from .pipeline import CrawlResult, crawl_one, discover_from_list

__all__ = ["Fetcher", "crawl_one", "discover_from_list", "CrawlResult"]

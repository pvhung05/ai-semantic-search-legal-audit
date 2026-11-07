"""Crawler vbpl.vn: Next.js App Router + Server Actions.

Luong hoat dong:
  seed_actions()       seed cac Server Action ID vao vanban.action_config
  discover()           duyet list theo phan trang (action 'list'), enqueue vao vanban.crawl_queue
  crawl_one(id_ref)    GET detail HTML + POST lien_quan + POST luoc_do + POST vbhn
                       -> upsert vao vanban.documents, vanban.document_content, vanban.document_relations
  seed_catalogs()      goi action danh_muc & co_quan -> seed danhmuc.loai_vanban, danhmuc.coquan_banhanh, danhmuc.linhvuc
"""
from .fetcher import Fetcher
from .pipeline import CrawlResult, crawl_one, discover_from_list

__all__ = ["Fetcher", "crawl_one", "discover_from_list", "CrawlResult"]

"""Tien ich chuyen HTML (toan van Word tu vbpl.vn) -> text thuan.

Dung chung boi service crawl (parse noi dung meta) va service doi sanh
(sinh chunk tu vanban.node). Khong phu thuoc vao bat ky service nao.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup


def html_doc_to_text(html_fragment: str) -> str:
    """Chuyen HTML Word (toan van) -> text giu cau truc xuong dong gan nhu goc:
    <br> va the block -> \\n; cell bang -> TAB."""
    if not html_fragment:
        return ""
    doc = BeautifulSoup(html_fragment, "lxml")
    body = doc.body or doc
    for br in body.find_all("br"):
        br.replace_with("\n")
    for tag_name in ("p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
        for t in body.find_all(tag_name):
            t.append("\n")
    for td in body.find_all(("td", "th")):
        td.append("\t")
    text = body.get_text()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[    ]+", " ", text)
    return text.strip()

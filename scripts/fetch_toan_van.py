"""Fetch HTML toan van van ban tu vbpl.vn qua Server Action.

Action: 233848b47c25357313670674c2dc84e482ce54da (Toan van)
Response text/x-component dang:
    0:["$@1",["<buildId>",null]]
    2:T<hexlen>,<html>...</html>
    1:"$2"

Script loai bo prefix (den truoc <html>) va suffix (sau </html>) de tra ve HTML sach.

Vi du:
    python scripts/fetch_toan_van.py 66801 --out doc_66801.html
    python scripts/fetch_toan_van.py 66801 --pretty
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.crawl_vbpl.fetcher import BASE, Fetcher  # noqa: E402

ACTION_TOAN_VAN = "233848b47c25357313670674c2dc84e482ce54da"

_HTML_DOC_RE = re.compile(r"<html[^>]*>.*?</html>", re.S | re.I)


def fetch_toan_van_html(id_ref: str) -> str:
    """Goi action Toan van, loai bo prefix/suffix RSC, tra ve HTML sach."""
    fetcher = Fetcher()
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}"
    body = json.dumps([id_ref], ensure_ascii=False)
    r = fetcher.rsc(ACTION_TOAN_VAN, body, referer=url)
    if r.status_code != 200:
        raise RuntimeError(f"Action tra ve {r.status_code}: {r.text[:200]}")
    m = _HTML_DOC_RE.search(r.text)
    if not m:
        raise RuntimeError(
            f"Khong tim thay <html>...</html>. 300 ky tu dau:\n{r.text[:300]}"
        )
    return m.group(0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("id_ref", help="ID vbpl (vd: 66801)")
    ap.add_argument("--out", help="File HTML de ghi (mac dinh: stdout)")
    args = ap.parse_args()

    html = fetch_toan_van_html(args.id_ref)
    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"Da ghi {args.out} ({len(html)} ky tu)")
    else:
        print(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())

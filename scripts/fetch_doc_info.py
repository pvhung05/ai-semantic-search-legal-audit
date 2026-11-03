"""Fetch JSON Thong tin van ban tu vbpl.vn qua Server Action.

Action: 0fb12b3561faa05adec51a82efb3e4f4f427f07b (Thong tin van ban)
Response text/x-component, trong do dong '1:{...}' chua JSON day du.

Vi du:
    python scripts/fetch_doc_info.py 66801
    python scripts/fetch_doc_info.py 66801 --out doc_66801.json
    python scripts/fetch_doc_info.py 66801 --pretty
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.crawl.fetcher import BASE, Fetcher  # noqa: E402

ACTION_DOC_INFO = "0fb12b3561faa05adec51a82efb3e4f4f427f07b"


def _extract_info_json(rsc_text: str) -> dict:
    """Response co dang:
      0:["$@1", ...]
      2:T<hexlen>,<html>...</html>1:{...JSON thong tin van ban...}
    JSON nam ngay sau '</html>1:' va chay den het response.
    """
    marker = "</html>1:"
    idx = rsc_text.rfind(marker)
    if idx < 0:
        # Fallback: tim dau '{"id":' cuoi cung
        idx = rsc_text.rfind('{"id":')
        if idx < 0:
            raise RuntimeError(
                f"Khong tim thay JSON info. 300 ky tu cuoi:\n{rsc_text[-300:]}"
            )
        start = idx
    else:
        start = idx + len(marker)
    return json.loads(rsc_text[start:].strip())


def fetch_doc_info(id_ref: str) -> dict:
    """Goi action 'Thong tin van ban' va tra ve JSON object day du."""
    fetcher = Fetcher()
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}"
    body = json.dumps([id_ref], ensure_ascii=False)
    r = fetcher.rsc(ACTION_DOC_INFO, body, referer=url)
    if r.status_code != 200:
        raise RuntimeError(f"Action tra ve {r.status_code}: {r.text[:200]}")
    return _extract_info_json(r.text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("id_ref", help="ID vbpl (vd: 66801)")
    ap.add_argument("--out", help="File JSON de ghi output (mac dinh: stdout)")
    ap.add_argument("--pretty", action="store_true", help="Format JSON de doc")
    args = ap.parse_args()

    data = fetch_doc_info(args.id_ref)
    indent = 2 if args.pretty else None
    text = json.dumps(data, ensure_ascii=False, indent=indent)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Da ghi {args.out} ({len(text)} ky tu)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

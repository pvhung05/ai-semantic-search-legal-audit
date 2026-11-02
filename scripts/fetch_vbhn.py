"""Fetch JSON Van ban hop nhat (VBHN) tu vbpl.vn qua Server Action.

Action: 0932c3801e9e99306fe7e694562e44ba55134662 (VBHN)
Response text/x-component, dong '1:[...]' chua list cac nhom VBHN.

Vi du:
    python scripts/fetch_vbhn.py 66801
    python scripts/fetch_vbhn.py 66801 --out vbhn_66801.json
    python scripts/fetch_vbhn.py 66801 --pretty
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

from app.crawl_vbpl.fetcher import BASE, Fetcher  # noqa: E402
from app.crawl_vbpl.parser import parse_rsc_payload  # noqa: E402

ACTION_VBHN = "0932c3801e9e99306fe7e694562e44ba55134662"


def fetch_vbhn(id_ref: str) -> list[dict]:
    """Goi action VBHN va tra ve list nhom VBHN:
    [ { vbhnDocument: {...}, mergedDocuments: [...] }, ... ]
    """
    fetcher = Fetcher()
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}"
    body = json.dumps([id_ref], ensure_ascii=False)
    r = fetcher.rsc(ACTION_VBHN, body, referer=url)
    if r.status_code != 200:
        raise RuntimeError(f"Action tra ve {r.status_code}: {r.text[:200]}")
    payload = parse_rsc_payload(r.text, line_id="1")
    if payload is None:
        raise RuntimeError(
            f"Khong parse duoc dong '1:'. 300 ky tu dau:\n{r.text[:300]}"
        )
    return payload if isinstance(payload, list) else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("id_ref", help="ID vbpl (vd: 66801)")
    ap.add_argument("--out", help="File JSON de ghi output (mac dinh: stdout)")
    ap.add_argument("--pretty", action="store_true", help="Format JSON de doc")
    args = ap.parse_args()

    data = fetch_vbhn(args.id_ref)
    indent = 2 if args.pretty else None
    text = json.dumps(data, ensure_ascii=False, indent=indent)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Da ghi {args.out} ({len(text)} ky tu, {len(data)} nhom VBHN)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

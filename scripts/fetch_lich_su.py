"""Fetch JSON Lich su chinh sua (luoc do - tac dong hieu luc) tu vbpl.vn.

Action: fe4862cb550ced8ac0057edfdf498bca2229be52 (Lich su chinh sua)
Response text/x-component dang:
    0:["$@1",["<buildId>",null]]
    1:[...danh sach item lich su + lifecycle...]

Script bo prefix dong '0:' va chi tra ve payload cua dong '1:'.

Moi item co dang:
    { id, status, sourceDocId, title, effFrom, ... }
Item khong co sourceDocId la lifecycle cua chinh van ban A:
    - 'Văn bản được ban hành'
    - 'Văn bản có hiệu lực'

Vi du:
    python scripts/fetch_lich_su.py 66801 --pretty
    python scripts/fetch_lich_su.py 66801 --out lichsu_66801.json
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
from app.crawl.parser import parse_rsc_payload  # noqa: E402

ACTION_LICH_SU = "fe4862cb550ced8ac0057edfdf498bca2229be52"


def fetch_lich_su(id_ref: str) -> list[dict]:
    """Goi action Lich su chinh sua va tra ve list item (bo prefix '0:')."""
    fetcher = Fetcher()
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}"
    body = json.dumps([id_ref], ensure_ascii=False)
    r = fetcher.rsc(ACTION_LICH_SU, body, referer=url)
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

    data = fetch_lich_su(args.id_ref)
    indent = 2 if args.pretty else None
    text = json.dumps(data, ensure_ascii=False, indent=indent)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        lifecycle = sum(1 for it in data if not it.get("sourceDocId"))
        print(f"Da ghi {args.out} ({len(text)} ky tu, "
              f"{len(data)} item - {lifecycle} lifecycle, {len(data) - lifecycle} tac dong)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

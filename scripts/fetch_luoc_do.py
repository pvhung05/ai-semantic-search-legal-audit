"""Fetch JSON Luoc do (lien_quan - quan he 2 chieu) tu vbpl.vn qua Server Action.

Action: 4a3423ce75290ef83a022333ee187acf4d38d3fb (Luoc do - FULL 2 chieu)
Response text/x-component, dong '1:{...}' chua object voi 2 key chinh:
  - documentNamesByType  : A tac dong B (can cu, dan chieu, huong dan, sua doi, thay the)
  - documentNamesBySource: B tac dong A (bi bai bo, duoc dan chieu, VBHN, bi sua doi)

Key so trong moi dict la MA loai quan he vbpl:
  1  = Bai bo mot phan
  3  = Can cu
  4  = Dan chieu
  7  = VBHN (van ban hop nhat)
  9  = Huong dan ap dung
  10 = Sua doi, bo sung
  12 = Thay the

Vi du:
    python scripts/fetch_luoc_do.py 66801
    python scripts/fetch_luoc_do.py 66801 --out luocdo_66801.json
    python scripts/fetch_luoc_do.py 66801 --pretty
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

ACTION_LUOC_DO = "4a3423ce75290ef83a022333ee187acf4d38d3fb"


def fetch_luoc_do(id_ref: str) -> dict:
    """Goi action Luoc do (lien_quan FULL) va tra ve dict:
      { documentNamesByType: {...}, documentNamesBySource: {...} }
    """
    fetcher = Fetcher()
    url = f"{BASE}/van-ban/chi-tiet/x--{id_ref}"
    body = json.dumps([id_ref], ensure_ascii=False)
    r = fetcher.rsc(ACTION_LUOC_DO, body, referer=url)
    if r.status_code != 200:
        raise RuntimeError(f"Action tra ve {r.status_code}: {r.text[:200]}")
    payload = parse_rsc_payload(r.text, line_id="1")
    if payload is None:
        raise RuntimeError(
            f"Khong parse duoc dong '1:'. 300 ky tu dau:\n{r.text[:300]}"
        )
    if not isinstance(payload, dict):
        return {"documentNamesByType": {}, "documentNamesBySource": {}}
    return {
        "documentNamesByType": payload.get("documentNamesByType") or {},
        "documentNamesBySource": payload.get("documentNamesBySource") or {},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("id_ref", help="ID vbpl (vd: 66801)")
    ap.add_argument("--out", help="File JSON de ghi output (mac dinh: stdout)")
    ap.add_argument("--pretty", action="store_true", help="Format JSON de doc")
    args = ap.parse_args()

    data = fetch_luoc_do(args.id_ref)
    indent = 2 if args.pretty else None
    text = json.dumps(data, ensure_ascii=False, indent=indent)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        n_type = sum(len(v) for v in data["documentNamesByType"].values())
        n_src = sum(len(v) for v in data["documentNamesBySource"].values())
        print(f"Da ghi {args.out} ({len(text)} ky tu, "
              f"ByType: {n_type} VB, BySource: {n_src} VB)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

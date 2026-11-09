"""Fetch CAY phan cap noi dung (Chuong/Dieu/Khoan/Diem) tu vbpl.vn.

Action: 31572a1d85cf23708d9875b486a76c7a3e2af300 (van ban da chia cap).
Response text/x-component: dong '1:' la cay JSON, nhung noi dung Dieu/Khoan/Diem
duoc danh trung vao cac text-literal 'T<hexlen>,...' va tham chieu bang '$<id>'.
Script boc tach theo do dai (parse_rsc_flight) roi noi lai (resolve_rsc_refs) de
duoc cay day du da inline.

Moi node:
  key, id       : UUID node
  title         : tieu de ("Chuong I\\n...", "Dieu 1. ...")
  level         : Chapter | Article | Clause | Point
  ptype         : ma cap (2=Chuong, 5=Dieu, ...)
  orderIndex    : thu tu phang trong van ban
  isLeaf        : true -> node la (co content day du)
  content       : {title, content} - content la HTML (<br>) cua node la
  children      : danh sach node con
  effFrom/effTo : hieu luc node (neu co)

Vi du:
    python scripts/fetch_cay_dieu.py 66801
    python scripts/fetch_cay_dieu.py 66801 --out cay_66801.json --pretty
    python scripts/fetch_cay_dieu.py 66801 --tree        # chi in khung cay
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

from app.crawl.doc_api import fetch_cay_noidung  # noqa: E402
from app.crawl.fetcher import Fetcher  # noqa: E402


def _count(nodes: list[dict], acc: dict[str, int]) -> None:
    for n in nodes:
        acc[n.get("level") or "?"] = acc.get(n.get("level") or "?", 0) + 1
        _count(n.get("children") or [], acc)


def _print_tree(nodes: list[dict], depth: int = 0) -> None:
    for n in nodes:
        title = (n.get("title") or "").replace("\n", " ").strip()
        print(f"{'  ' * depth}[{n.get('level')}] {title[:80]}")
        _print_tree(n.get("children") or [], depth + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("id_ref", help="ID vbpl (vd: 66801)")
    ap.add_argument("--out", help="File JSON de ghi output (mac dinh: stdout)")
    ap.add_argument("--pretty", action="store_true", help="Format JSON de doc")
    ap.add_argument("--tree", action="store_true", help="Chi in khung cay (khong JSON)")
    args = ap.parse_args()

    tree = fetch_cay_noidung(Fetcher(), args.id_ref)

    if args.tree:
        _print_tree(tree)
        acc: dict[str, int] = {}
        _count(tree, acc)
        print("---")
        print(" ".join(f"{k}={v}" for k, v in sorted(acc.items())))
        return 0

    text = json.dumps(tree, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        acc = {}
        _count(tree, acc)
        print(f"Da ghi {args.out} ({len(text)} ky tu, "
              f"{len(tree)} node goc, " + " ".join(f"{k}={v}" for k, v in sorted(acc.items())) + ")")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

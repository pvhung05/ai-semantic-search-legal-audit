"""Wrapper mong cho service crawl. Logic that o `app/crawl/cli.py`.

Tuong duong: `python -m app.crawl.cli <lenh>`.
Luu y: lenh `build-cay` da chuyen sang service doi sanh:
    python -m app.doisanh.cli build-cay ...
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.crawl.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

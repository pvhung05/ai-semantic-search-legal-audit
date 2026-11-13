"""Lenh chuan cua repo, chay duoc tren Windows lan Linux (may dev khong co `make`).

    python tasks.py setup   # tao .venv + cai dependency (pin trong requirements.txt) + pytest
    python tasks.py test    # pytest offline (bo test can LLM/DB that)
    python tasks.py lint    # kiem tra cu phap (repo chua dung linter; quyet dinh: khong them ruff)
    python tasks.py check   # lint + test; phai pass truoc khi commit
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable
TEST_DEPS = ["pytest==9.1.1", "pytest-asyncio>=0.23"]
CODE_DIRS = ["app", "scripts", "tests", "tasks.py"]


def run(*cmd: str, env: dict[str, str] | None = None) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=ROOT, env=env)


def setup() -> int:
    if not VENV_PY.exists() and run(sys.executable, "-m", "venv", str(VENV)):
        return 1
    rc = run(str(VENV_PY), "-m", "pip", "install", "-r", "requirements.txt", *TEST_DEPS)
    if not (ROOT / ".env").exists():
        print("! Chua co .env: tao file nay voi it nhat DB_URL=... "
              "(danh sach bien: app/core/config.py)")
    return rc


def test() -> int:
    env = dict(os.environ)
    if "DB_URL" not in env and not (ROOT / ".env").exists():
        # Settings() bat buoc DB_URL ngay khi import; test offline khong ket noi DB nen gia tri gia la du.
        env["DB_URL"] = "postgresql://offline:offline@127.0.0.1:1/offline"
    return run(PY, "-m", "pytest", "-m", "not llm and not integration", "-q", env=env)


def lint() -> int:
    return run(PY, "-m", "compileall", "-q", *CODE_DIRS)


def check() -> int:
    return lint() or test()


TASKS = {"setup": setup, "test": test, "lint": lint, "check": check}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        sys.exit(f"Dung: python tasks.py {{{'|'.join(TASKS)}}}")
    sys.exit(TASKS[sys.argv[1]]())

"""Lenh chuan cua repo, chay duoc tren Windows lan Linux (may dev khong co `make`).

    python tasks.py setup   # tao .venv + cai dependency (pin trong requirements.txt) + pytest
    python tasks.py test    # pytest offline (bo test can LLM/DB that)
    python tasks.py lint    # kiem tra cu phap (repo chua dung linter; quyet dinh: khong them ruff)
    python tasks.py docs    # CANH BAO (khong fail): link hong trong *.md, code doi ma tai lieu module khong doi
    python tasks.py check   # lint + test (quyet dinh exit code) + docs (chi canh bao)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

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


DOC_NAMES = ("ARCHITECTURE.md", "CONSTRAINTS.md")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def broken_links(path: Path, text: str) -> list[str]:
    """Link markdown tuong doi tro toi tep/thu muc khong ton tai (bo qua URL, #anchor, code fence)."""
    out, in_fence = [], False
    for no, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for target in LINK_RE.findall(line):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            if not (path.parent / target.split("#")[0]).exists():
                out.append(f"{path.relative_to(ROOT).as_posix()}:{no} -> {target}")
    return out


def stale_docs(changed: set[str], doc_dirs: set[str]) -> dict[str, list[str]]:
    """{thu muc tai lieu: [tep code da doi]} khi code doi ma khong tai lieu nao cua module (hoac to tien) doi."""
    changed_docs = {str(PurePosixPath(p).parent) for p in changed if PurePosixPath(p).name in DOC_NAMES}
    out: dict[str, list[str]] = {}
    for p in sorted(changed):
        pp = PurePosixPath(p)
        if pp.suffix == ".md":
            continue
        owners = [str(a) for a in pp.parents if str(a) in doc_dirs]
        if owners and not any(o in changed_docs for o in owners):
            out.setdefault(owners[0], []).append(p)
    return out


def _git(*args: str) -> list[str]:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return r.stdout.split("\n") if r.returncode == 0 else []


def _changed_files() -> set[str]:
    """Thay doi cua branch so voi diem re tu DOCS_BASE (mac dinh main) + thay doi chua commit."""
    base = (_git("merge-base", "HEAD", os.environ.get("DOCS_BASE", "main")) or [""])[0]
    files = _git("diff", "--name-only", f"{base}...HEAD") if base else []
    files += _git("diff", "--name-only", "HEAD") + _git("ls-files", "--others", "--exclude-standard")
    return {f for f in files if f}


def docs() -> int:
    tracked = [f for f in _git("ls-files", "--cached", "--others", "--exclude-standard") if f]
    warnings = []
    for f in tracked:
        if f.endswith(".md") and (ROOT / f).exists():
            warnings += broken_links(ROOT / f, (ROOT / f).read_text(encoding="utf-8"))
    doc_dirs = {str(PurePosixPath(f).parent) for f in tracked if PurePosixPath(f).name in DOC_NAMES}
    for d, files in stale_docs(_changed_files(), doc_dirs).items():
        warnings.append(f"code doi nhung {d}/{{ARCHITECTURE,CONSTRAINTS}}.md khong doi: {', '.join(files)}")
    for w in warnings:
        print("WARN docs:", w)
    print(f"docs: {len(warnings)} canh bao (khong chan commit)")
    return 0


def check() -> int:
    rc = lint() or test()
    docs()
    return rc


TASKS = {"setup": setup, "test": test, "lint": lint, "docs": docs, "check": check}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        sys.exit(f"Dung: python tasks.py {{{'|'.join(TASKS)}}}")
    sys.exit(TASKS[sys.argv[1]]())

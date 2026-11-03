"""Chuan hoa text van ban luat truoc khi parse va so sanh."""
from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"[ \t   ]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_HYPHEN_WRAP_RE = re.compile(r"-\n(?=\w)")
_SMART_QUOTES = {
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‘": "'", "’": "'",
}
_DASHES = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
}


def _thay_ky_tu(text: str) -> str:
    for old, new in {**_SMART_QUOTES, **_DASHES}.items():
        text = text.replace(old, new)
    return text


def chuan_hoa_dong(line: str) -> str:
    """Chuan hoa mot dong: NFC, bo khoang trang kep, trim."""
    line = unicodedata.normalize("NFC", line)
    line = _thay_ky_tu(line)
    line = _WS_RE.sub(" ", line)
    return line.strip()


def chuan_hoa_text(text: str) -> str:
    """Chuan hoa toan khoi text truoc khi parse.

    - NFC + thay ky tu "thong minh"
    - Noi tu bi ngat dong boi dau gach noi
    - Chuan hoa khoang trang moi dong
    - Rut gon 3+ dong trong lien tiep ve 2 dong
    """
    text = unicodedata.normalize("NFC", text)
    text = _thay_ky_tu(text)
    text = _HYPHEN_WRAP_RE.sub("", text)
    lines = [chuan_hoa_dong(line) for line in text.splitlines()]
    text = "\n".join(lines)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def chuan_hoa_so_sanh(text: str) -> str:
    """Chuan hoa manh de so sanh fuzzy nguyen van: thuong, bo dau cach lien tiep."""
    text = unicodedata.normalize("NFC", text)
    text = _thay_ky_tu(text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()

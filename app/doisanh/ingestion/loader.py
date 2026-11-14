"""Doc file luat (.docx, .pdf, .txt) ra text tho."""
from __future__ import annotations

from pathlib import Path


def doc_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def doc_docx(path: Path) -> str:
    try:
        import docx
    except ImportError as exc:
        raise RuntimeError("Chua cai python-docx. pip install python-docx") from exc
    document = docx.Document(str(path))
    parts: list[str] = []
    for para in document.paragraphs:
        parts.append(para.text)
    for table in document.tables:
        for row in table.rows:
            seen_cells = set()
            for cell in row.cells:
                if cell._tc not in seen_cells:
                    seen_cells.add(cell._tc)
                    parts.append(cell.text)
    return "\n".join(parts)


def doc_pdf(path: Path) -> str:
    """Doc PDF luat VN. Sort text theo thu tu doc tu nhien (y,x) de xu ly 2-column."""
    try:
        import pymupdf  # pymupdf
    except ImportError as exc:
        raise RuntimeError("Chua cai pymupdf. pip install pymupdf") from exc
    with pymupdf.open(str(path)) as pdf:
        return "\n".join(page.get_text("text", sort=True) for page in pdf)


def doc_file(path: Path) -> str:
    """Doc file theo duoi file. Nem RuntimeError neu khong ho tro."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".txt":
        return doc_txt(path)
    if ext == ".docx":
        return doc_docx(path)
    if ext == ".pdf":
        return doc_pdf(path)
    if ext == ".doc":
        raise RuntimeError("File .doc (Word cu) khong doc truc tiep duoc. "
                           "Hay mo bang Word/LibreOffice roi Save As .docx hoac .pdf.")
    raise RuntimeError(f"Khong ho tro duoi file: {ext} (chi nhan .docx, .pdf, .txt)")

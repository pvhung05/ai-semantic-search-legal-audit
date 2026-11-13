"""Kiem tra/chuan hoa ket qua audit truoc khi tra ve: snippet LLM co khop nguyen van
khong, va dinh vi can cu (Dieu/khoan/diem). Tach khoi route de de test rieng."""
from __future__ import annotations

import re


def chuan_so_sanh(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def la_snippet_hop_le(snippet: str, nguyen_van: str) -> bool:
    """Snippet LLM chep la 1 doan con THUC SU cua nguyen van (chep dung, ngan hon)."""
    ns, nf = chuan_so_sanh(snippet), chuan_so_sanh(nguyen_van)
    return bool(ns) and ns in nf and len(ns) < len(nf)


def cat_theo_pham_vi(de_xuat: str, snippet: str, nguyen_van: str) -> str:
    """LLM hay chep lai CA doan vao de_xuat_sua thay vi chi phan sai -> bo phan dau/cuoi trung
    nguyen van nam ngoai snippet, de de_xuat_sua thay DUNG cho snippet (track-change khong lap chu)."""
    gon = lambda s: re.sub(r"\s+", " ", s or "").strip()  # noqa: E731
    d, sn, nv = gon(de_xuat), gon(snippet), gon(nguyen_van)
    i = nv.find(sn) if sn else -1
    if not d or i < 0:
        return de_xuat
    truoc, sau = nv[:i].strip(), nv[i + len(sn):].strip()
    cat = d
    if truoc and cat.startswith(truoc):
        cat = cat[len(truoc):].strip()
    if sau and cat.endswith(sau):
        cat = cat[: -len(sau)].strip()
    return de_xuat if cat == d else cat


def la_de_xuat_trung_lap(de_xuat: str, snippet: str, nguyen_van: str) -> bool:
    """Kiem tra xem de_xuat_sua co bi trung lap hoac giong het noi dung sai/nguyen van khong.

    Neu giong het thi khong phai la de xuat sua hop le (thuong do LLM chep lai doan sai).
    """
    if not de_xuat or not de_xuat.strip():
        return False
    d = chuan_so_sanh(de_xuat)
    s = chuan_so_sanh(snippet)
    nv = chuan_so_sanh(nguyen_van)
    return bool(d) and (d == s or d == nv)


def la_de_xuat_menh_lenh_bo(de_xuat: str) -> bool:
    """Kiem tra xem de_xuat co phai la cau menh lenh/huong dan yeu cau bo doan vi pham thay vi chuoi thay the."""
    if not de_xuat or not de_xuat.strip():
        return False
    d = chuan_so_sanh(de_xuat).rstrip(".:,;")
    cum_tu = (
        "bỏ", "bãi bỏ", "loại bỏ", "cần bỏ", "nên bỏ", "đề nghị bỏ", "xóa bỏ", "hủy bỏ",
        "bỏ đoạn này", "bỏ quy định này", "loại bỏ quy định này", "bãi bỏ quy định này",
        "bỏ phần này", "bỏ nội dung này", "loại bỏ nội dung này",
    )
    if d in cum_tu:
        return True
    return any(d.startswith(p + " ") for p in ("cần bỏ", "nên bỏ", "đề nghị bỏ", "yêu cầu bỏ", "bãi bỏ", "loại bỏ"))


def vi_tri_can_cu(u: dict) -> str:
    """Vi tri can cu phap ly: 'Chuong .. Dieu X khoan Y diem Z' tu ung vien khoan me."""
    parts = []
    if u.get("phan"):
        parts.append(u["phan"])
    if u.get("chuong"):
        parts.append(u["chuong"])
    if u.get("so_dieu"):
        parts.append(f"Điều {u['so_dieu']}")
    if u.get("so_khoan"):
        parts.append(f"khoản {u['so_khoan']}")
    if u.get("diem"):
        parts.append(f"điểm {u['diem']}")
    return " ".join(parts)


def tach_can_cu_goc(s: str | None, nd_sau_sua: str | None = None) -> str:
    """Tach bo khoi prefix tac dong danh cho LLM ([CAN CU NAY ...] va 'Noi dung sau khi sua: ...') neu co.

    Dung de dam bao dau ra trich_dan hien thi tren UI/DOCX chi chua nguyen van can cu phap ly goc.
    """
    if not s:
        return ""
    parts = s.split("\n---\n")
    cleaned: list[str] = []
    for p in parts:
        t = p.strip()
        if t.startswith("[CĂN CỨ NÀY") or t.startswith("[CAN CU NAY"):
            idx = t.find("]")
            if idx != -1:
                rest = t[idx + 1:].strip()
                if rest.lower().startswith("nội dung sau khi sửa:") or rest.lower().startswith("noi dung sau khi sua:"):
                    after_label = rest.split(":", 1)[1].strip()
                    if nd_sau_sua and after_label.startswith(nd_sau_sua.strip()):
                        rest = after_label[len(nd_sau_sua.strip()):].strip()
                    else:
                        m = re.search(r'\n(?=(?:Điều|Khoản|\d+\.))', rest, flags=re.IGNORECASE)
                        if m:
                            rest = rest[m.start():].strip()
                        else:
                            lines = rest.splitlines()
                            rest = "\n".join(lines[1:]).strip()
                cleaned.append(rest)
                continue
        cleaned.append(t)
    return "\n---\n".join(c for c in cleaned if c)

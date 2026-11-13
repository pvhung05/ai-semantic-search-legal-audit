"""Danh dau cac doan VI_PHAM tu ket qua audit len file docx du thao.

Moi phat hien VI_PHAM:
  - `noi_dung_du_thao` = doan SAI (snippet, LLM chep chinh xac tu du thao).
  - `de_xuat_sua`      = doan do SAU khi sua.
-> Tim snippet sai trong docx, DIFF tung tu giua snippet cu va ban da sua: chi phan KHAC
   moi thanh Track Change THAT cua Word - tu bi bo boc <w:del>, tu them boc <w:ins>, phan
   giong giu nguyen. Word tu to mau/gach + VE GACH DOC LE TRAI, cho BAT/TAT hien thi va
   Accept/Reject. Comment "AI LEGAL" neo quanh vung sua.
   Neu khong co de_xuat_sua / khong dinh vi duoc snippet -> fallback: to do ca doan + comment.
"""
from __future__ import annotations

import datetime
import difflib
import itertools
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

_DO = RGBColor(0xC0, 0x00, 0x00)
_DO_HEX = "C00000"
_MIN_LEN = 8          # bo qua paragraph qua ngan khi so khop
_FUZZ = 0.85          # nguong fuzzy fallback (khop ~ quy uoc fuzz>=85 cua du an)
_REV_ID = itertools.count(1)   # w:id duy nhat cho moi <w:ins>/<w:del>
_REV_DATE = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _tach_can_cu_goc(s: str | None, nd_sau_sua: str | None = None) -> str:
    """Tach bo khoi prefix tac dong [CAN CU NAY ...] va 'Noi dung sau khi sua: ...' neu co."""
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
                        # Tim vi tri bat dau cua text quy pham goc (Dieu / Khoan / STT)
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


def _noi_dung_comment(vp: dict) -> str:
    cc = vp.get("can_cu_phap_ly") or {}
    blocks: list[str] = []

    # 1. Can cu phap ly goc (da loc bo khoi header tac dong trung lap)
    dinh_danh = " – ".join(x for x in (cc.get("so_hieu"), cc.get("vi_tri")) if x)
    if cc.get("ten_van_ban"):
        dinh_danh = f"{dinh_danh} ({cc['ten_van_ban']})" if dinh_danh else cc["ten_van_ban"]

    goc_text = _tach_can_cu_goc(cc.get("trich_dan"), cc.get("noi_dung_sau_sua"))
    phan_goc = []
    if dinh_danh:
        phan_goc.append("Căn cứ pháp lý: " + dinh_danh)
    if goc_text:
        phan_goc.append(goc_text)
    if phan_goc:
        blocks.append("\n".join(phan_goc))

    # 2. Can cu phap ly tac dong (neu co sua doi / bai bo)
    if cc.get("da_sua"):
        vt = cc.get("vi_tri") or "Căn cứ"
        nguon = cc.get("sua_boi", "")
        ngay = cc.get("ngay_hieu_luc", "")
        hau = f" (hiệu lực {ngay})" if ngay else ""

        phan_tac_dong = []
        if cc.get("da_het_hieu_luc"):
            phan_tac_dong.append(f"⚠ {vt} đã bị bãi bỏ bởi {nguon}{hau} — không còn hiệu lực.")
        else:
            note_line = f"⚠ {vt} đã được sửa đổi bởi {nguon}{hau}"
            nd_sau_sua = cc.get("noi_dung_sau_sua", "").strip()
            if nd_sau_sua:
                note_line += ":"
                phan_tac_dong.append(note_line)
                phan_tac_dong.append(nd_sau_sua)
            else:
                phan_tac_dong.append(note_line + ".")

        if phan_tac_dong:
            blocks.append("\n".join(phan_tac_dong))

    # Giua 2 phan cach nhau 1 dong trong (\n\n)
    return "\n\n".join(blocks) or "Vi phạm (AI LEGAL)."


def _tim_paragraph(norm_paras: list[str], target: str) -> list[int]:
    """Tra ve chi so paragraph khop `target`. Uu tien chua-nhau (segment nhieu dong),
    nguoc lai fuzzy 1 paragraph tot nhat."""
    out = [i for i, pt in enumerate(norm_paras)
           if len(pt) >= _MIN_LEN and (pt in target or target in pt)]
    if out:
        return out
    best, bi = 0.0, None
    for i, pt in enumerate(norm_paras):
        if len(pt) < _MIN_LEN:
            continue
        r = difflib.SequenceMatcher(None, pt, target).ratio()
        if r > best:
            best, bi = r, i
    return [bi] if bi is not None and best >= _FUZZ else []


def _tim_vi_tri(full: str, target: str) -> tuple[int, int] | None:
    """Vi tri (start, end) cua `target` trong `full`: thu khop nguyen van, roi khop
    linh hoat khoang trang (snippet LLM chep co the lech dau cach)."""
    i = full.find(target)
    if i >= 0:
        return (i, i + len(target))
    toks = [t for t in target.split() if t]
    if not toks:
        return None
    m = re.search(r"\s+".join(re.escape(t) for t in toks), full)
    return (m.start(), m.end()) if m else None


def _them_gach_le(para) -> None:
    """Gach doc do o le trai paragraph (change bar) - danh dau doan co sua, cho gon."""
    pPr = para._p.get_or_add_pPr()
    if pPr.find(qn("w:pBdr")) is not None:
        return
    pBdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    for k, v in (("w:val", "single"), ("w:sz", "18"), ("w:space", "4"), ("w:color", _DO_HEX)):
        left.set(qn(k), v)
    pBdr.append(left)
    pPr.append(pBdr)


def _tach_tu(s: str) -> list[str]:
    """Tach thanh token giu nguyen khoang trang (de ghep lai khong lech dau cach)."""
    return re.findall(r"\s+|\S+", s)


def _them_revision(para, loai: str, text: str, tac_gia: str) -> None:
    """Noi 1 revision Word vao cuoi para: loai='del' (xoa, dung w:delText) hoac 'ins' (them).
    Word tu to mau theo nguoi sua + ve gach doc le trai, cho Accept/Reject + bat/tat."""
    if not text:
        return
    el = OxmlElement(f"w:{loai}")
    el.set(qn("w:id"), str(next(_REV_ID)))
    el.set(qn("w:author"), tac_gia)
    el.set(qn("w:date"), _REV_DATE)
    r = OxmlElement("w:r")
    t = OxmlElement("w:delText" if loai == "del" else "w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    el.append(r)
    para._p.append(el)


def _diff_revision_vao_para(para, cu: str, moi: str, tac_gia: str) -> None:
    """So sanh tung tu `cu` vs `moi` -> noi vao para: giong = run thuong; tu bo = <w:del>;
    tu them = <w:ins>. Chi phan KHAC thanh track change."""
    a, b = _tach_tu(cu), _tach_tu(moi)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            para.add_run("".join(a[i1:i2]))
            continue
        if tag in ("delete", "replace"):
            _them_revision(para, "del", "".join(a[i1:i2]), tac_gia)
        if tag in ("insert", "replace"):
            _them_revision(para, "ins", "".join(b[j1:j2]), tac_gia)


def _thay_va_danh_dau(doc, para, raw_target: str, new_text: str,
                      noi_dung_cmt: str, tac_gia: str) -> bool:
    """Sua tai `raw_target` bang Track Change THAT: DIFF tung tu snippet cu vs ban da sua,
    tu bi bo boc <w:del>, tu them boc <w:ins>, phan giong giu nguyen. Word tu ve gach doc le
    + cho Accept/Reject. Neo comment quanh vung sua. True neu dinh vi duoc snippet.

    shortcut: build lai runs cua para -> mat dinh dang inline (bold/italic) cua rieng
    paragraph do; chap nhan vi du thao thuong 1 run. Nang cap khi can giu format.
    """
    full = para.text
    vt = _tim_vi_tri(full, raw_target)
    if vt is None:
        return False
    s, e = vt
    before, cu, after = full[:s], full[s:e], full[e:]
    for r in list(para.runs):
        r._element.getparent().remove(r._element)
    # head/tail luon la run thuong (co the rong) de neo comment o cap paragraph - hop le
    # ca khi thay doi nam dau/cuoi doan (run trong <w:ins>/<w:del> khong neo comment duoc).
    head = para.add_run(before)
    _diff_revision_vao_para(para, cu, new_text, tac_gia)
    tail = para.add_run(after)
    doc.add_comment([head, tail], text=noi_dung_cmt, author=tac_gia, initials="AI")
    return True


def danh_dau_vi_pham(docx_vao: str | Path, ket_qua: dict,
                     docx_ra: str | Path, tac_gia: str = "AI LEGAL") -> int:
    """Sua + danh dau cac VI_PHAM tren docx. Tra ve so phat hien da danh dau.

    `ket_qua`: nguyen JSON tu /audit (co `ket_qua.VI_PHAM`) hoac chinh dict {VI_PHAM: [...]}.
    VI_PHAM: giu `noi_dung_du_thao` (doan sai, gach ngang do) + them `de_xuat_sua`
    (da sua, gach chan do) + comment. Khong co de_xuat_sua / khong dinh vi duoc ->
    fallback to do ca doan chua no.
    """
    nhom = ket_qua.get("ket_qua", ket_qua) if isinstance(ket_qua, dict) else {}
    vi_phams = nhom.get("VI_PHAM", []) if isinstance(nhom, dict) else []

    doc = Document(str(docx_vao))
    paras = doc.paragraphs
    norm_paras = [_norm(p.text) for p in paras]

    n = 0
    for vp in vi_phams:
        raw_target = (vp.get("noi_dung_du_thao") or "").strip()
        target = _norm(raw_target)
        if not target:
            continue
        new_text = (vp.get("de_xuat_sua") or "").strip()
        noi_dung = _noi_dung_comment(vp)

        # Co ban sua -> thay snippet sai bang ban sua (to do phan moi) o doan dau tien chua no.
        if new_text:
            thay_duoc = False
            for i, pt in enumerate(norm_paras):
                if len(pt) >= _MIN_LEN and target in pt:
                    if _thay_va_danh_dau(doc, paras[i], raw_target, new_text, noi_dung, tac_gia):
                        norm_paras[i] = _norm(paras[i].text)  # cap nhat sau khi sua
                        n += 1
                        thay_duoc = True
                        break
            if thay_duoc:
                continue

        # Fallback: to do ca doan chua snippet + comment (khong thay the).
        for i in _tim_paragraph(norm_paras, target):
            runs = [r for r in paras[i].runs if r.text]
            if not runs:
                continue
            for r in runs:
                r.font.color.rgb = _DO
            _them_gach_le(paras[i])
            doc.add_comment(runs, text=noi_dung, author=tac_gia, initials="AI")
            n += 1

    doc.save(str(docx_ra))
    return n

"""Parse van ban luat Viet Nam thanh Chuong/Muc/Dieu/Khoan/Diem.

Theo quy uoc PLAN muc 6.2:
- Dieu  : ^Điều\\s+(\\d+[a-zđ]?)\\s*\\.?\\s*(.*)$
- Khoan : ^(\\d+[a-zđ]?)\\.\\s+
- Diem  : ^([a-zđ])\\)\\s+
- Can cu: dong ^Căn cứ\\s+ den dong trong hoac "Theo đề nghị"
- Nhay/trung so Dieu -> canh bao, khong dung
- so_dieu la str, cho phep '54a'
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingestion.normalize import chuan_hoa_text
from app.models.schemas import Dieu, Khoan, VanBanMeta, VanBanParsed

RE_CHUONG = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\s*[:\.\-]?\s*(.*)$", re.IGNORECASE)
RE_MUC = re.compile(r"^Mục\s+(\d+)\s*[:\.\-]?\s*(.*)$", re.IGNORECASE)
RE_DIEU = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*\.\s*(.*)$")  # Phai co dau cham sau so
RE_DIEU_MUC_LUC = re.compile(r"\.{3,}\s*\d+\s*$")  # 'Dieu N. Ten .... 15' kieu TOC
RE_KHOAN = re.compile(r"^(\d+[a-zđ]?)\.\s+(.*)$")
RE_DIEM = re.compile(r"^([a-zđ])\)\s+(.*)$")
RE_CAN_CU = re.compile(r"^Căn cứ\s+", re.IGNORECASE)
RE_THEO_DE_NGHI = re.compile(r"^(Theo đề nghị|Theo đề xuất)", re.IGNORECASE)
RE_SUA_DOI_TIEU_DE = re.compile(
    r"(Sửa đổi,?\s*bổ sung một số điều của|Luật sửa đổi,? bổ sung|Nghị định sửa đổi)",
    re.IGNORECASE,
)
RE_HIEU_LUC_DIEU = re.compile(r"Hiệu lực thi hành", re.IGNORECASE)
RE_NGAY_HL = re.compile(
    r"(có hiệu lực(?: thi hành)? (?:từ|kể từ) ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4}))",
    re.IGNORECASE,
)
RE_NGAY_HL_SO = re.compile(r"ngày\s+(\d{1,2})/(\d{1,2})/(\d{4})")
RE_DAU_NGOAC_KEP = re.compile(r"\"[^\"\n]*$")


def _so_dieu_num(so_dieu: str) -> int:
    """'54a' -> 54, '13' -> 13."""
    m = re.match(r"(\d+)", so_dieu)
    return int(m.group(1)) if m else 0


def _trong_ngoac_kep_chua_dong(buffer: str) -> bool:
    """Dem so dau " trong buffer; le nghia la ngoac kep chua dong."""
    return buffer.count('"') % 2 == 1


@dataclass
class _TrangThai:
    chuong_so: str | None = None
    chuong_ten: str | None = None
    muc_so: str | None = None
    muc_ten: str | None = None
    dieu_hien_tai: Dieu | None = None
    khoan_hien_tai: Khoan | None = None
    buffer_dong: list[str] = field(default_factory=list)


def _flush_buffer_vao_khoan(ts: _TrangThai) -> None:
    # Chi xu ly + xoa buffer khi dang trong 1 Khoan. Neu chua co Khoan,
    # GIU buffer de _flush_buffer_vao_dieu lay (dieu ngan/doan mo dau Dieu).
    if not ts.khoan_hien_tai:
        return
    if ts.buffer_dong:
        them = " ".join(ts.buffer_dong).strip()
        if them:
            ts.khoan_hien_tai.noi_dung = (
                ts.khoan_hien_tai.noi_dung + " " + them
                if ts.khoan_hien_tai.noi_dung
                else them
            )
    ts.buffer_dong.clear()


def _flush_buffer_vao_dieu(ts: _TrangThai) -> None:
    """Noi dung Dieu khi chua co Khoan nao (dieu ngan khong chia khoan)."""
    if ts.dieu_hien_tai and not ts.dieu_hien_tai.khoan and ts.buffer_dong:
        them = " ".join(ts.buffer_dong).strip()
        if them:
            ts.dieu_hien_tai.noi_dung = (
                ts.dieu_hien_tai.noi_dung + " " + them
                if ts.dieu_hien_tai.noi_dung
                else them
            )
    ts.buffer_dong.clear()


def _trich_can_cu(lines: list[str]) -> list[str]:
    """Lay cac dong Can cu lien tuc tu dau cho den dong trong hoac Theo de nghi."""
    can_cu: list[str] = []
    dang_doc = False
    for ln in lines:
        s = ln.strip()
        if RE_CAN_CU.match(s):
            dang_doc = True
            can_cu.append(s)
            continue
        if dang_doc:
            if not s or RE_THEO_DE_NGHI.match(s):
                break
            # dong noi tiep can cu truoc
            if RE_CAN_CU.match(s):
                can_cu.append(s)
            else:
                if can_cu:
                    can_cu[-1] = can_cu[-1] + " " + s
    return [c.strip() for c in can_cu if c.strip()]


def _la_van_ban_sua_doi(ten: str, dieu_list: list[Dieu]) -> bool:
    """Chi mark true khi ten van ban khop pattern 'Luat/Nghi dinh sua doi' hoac
    co Dieu voi tieu_de 'Sua doi, bo sung ... Nghi dinh/Luat so <sh>'."""
    if RE_SUA_DOI_TIEU_DE.search(ten or ""):
        return True
    for d in dieu_list:
        tieu_de = d.tieu_de or ""
        if RE_SUA_DOI_TIEU_DE.search(tieu_de) and re.search(r"\d+/\d+/", tieu_de):
            return True
    return False


def parse_van_ban(text: str, meta: VanBanMeta) -> VanBanParsed:
    """Parse text da chuan hoa thanh VanBanParsed."""
    text = chuan_hoa_text(text)
    lines = text.split("\n")
    ts = _TrangThai()
    dieu_list: list[Dieu] = []
    canh_bao: list[str] = []
    thu_tu_dieu = 0
    thu_tu_khoan = 0
    buffer_noi_dong = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            # ngat Khoan truoc khi doi phan khac
            _flush_buffer_vao_khoan(ts)
            _flush_buffer_vao_dieu(ts)
            buffer_noi_dong = ""
            continue

        # bao ve: dong hien tai nam trong ngoac kep chua dong -> coi la noi dung
        trong_ngoac = _trong_ngoac_kep_chua_dong(buffer_noi_dong)
        buffer_noi_dong += " " + line
        if trong_ngoac:
            if ts.khoan_hien_tai:
                ts.buffer_dong.append(line)
            elif ts.dieu_hien_tai:
                ts.buffer_dong.append(line)
            continue

        m = RE_CHUONG.match(line)
        if m:
            _flush_buffer_vao_khoan(ts)
            _flush_buffer_vao_dieu(ts)
            ts.chuong_so = m.group(1)
            ts.chuong_ten = (m.group(2) or "").strip() or None
            ts.muc_so = ts.muc_ten = None
            ts.khoan_hien_tai = None
            continue

        m = RE_MUC.match(line)
        if m:
            _flush_buffer_vao_khoan(ts)
            _flush_buffer_vao_dieu(ts)
            ts.muc_so = m.group(1)
            ts.muc_ten = (m.group(2) or "").strip() or None
            ts.khoan_hien_tai = None
            continue

        m = RE_DIEU.match(line)
        if m and RE_DIEU_MUC_LUC.search(line):
            # dong muc luc 'Dieu N. Ten ....... 15' -> bo qua
            continue
        if m:
            _flush_buffer_vao_khoan(ts)
            _flush_buffer_vao_dieu(ts)
            so_dieu = m.group(1)
            tieu_de = (m.group(2) or "").strip() or None

            # canh bao nhay/trung
            cur_num = _so_dieu_num(so_dieu)
            if dieu_list:
                prev_num = dieu_list[-1].so_dieu_num
                if cur_num == prev_num:
                    canh_bao.append(f"so_dieu trung lap: {so_dieu}")
                elif cur_num < prev_num:
                    canh_bao.append(f"so_dieu giam: {dieu_list[-1].so_dieu} -> {so_dieu}")
                elif cur_num > prev_num + 1:
                    canh_bao.append(f"nhay so_dieu: {dieu_list[-1].so_dieu} -> {so_dieu}")

            thu_tu_dieu += 1
            thu_tu_khoan = 0
            ts.dieu_hien_tai = Dieu(
                so_dieu=so_dieu,
                so_dieu_num=cur_num,
                tieu_de=tieu_de,
                noi_dung="",
                thu_tu=thu_tu_dieu,
                chuong_so=ts.chuong_so,
                chuong_ten=ts.chuong_ten,
                muc_so=ts.muc_so,
                muc_ten=ts.muc_ten,
            )
            ts.khoan_hien_tai = None
            dieu_list.append(ts.dieu_hien_tai)
            continue

        m = RE_DIEM.match(line)
        if m and ts.khoan_hien_tai:
            _flush_buffer_vao_khoan(ts)
            diem = m.group(1)
            noi_dung = (m.group(2) or "").strip()
            parent = ts.khoan_hien_tai
            # Diem = Khoan voi diem != None, parent = Khoan hien tai
            thu_tu_khoan += 1
            diem_khoan = Khoan(
                so_khoan=parent.so_khoan,
                diem=diem,
                noi_dung=noi_dung,
                thu_tu=thu_tu_khoan,
                parent_so_khoan=parent.so_khoan,
            )
            if ts.dieu_hien_tai:
                ts.dieu_hien_tai.khoan.append(diem_khoan)
            ts.khoan_hien_tai = diem_khoan
            continue

        m = RE_KHOAN.match(line)
        if m and ts.dieu_hien_tai:
            _flush_buffer_vao_khoan(ts)
            _flush_buffer_vao_dieu(ts)
            so_khoan = m.group(1)
            noi_dung = (m.group(2) or "").strip()
            thu_tu_khoan += 1
            khoan = Khoan(
                so_khoan=so_khoan,
                diem=None,
                noi_dung=noi_dung,
                thu_tu=thu_tu_khoan,
                parent_so_khoan=None,
            )
            ts.dieu_hien_tai.khoan.append(khoan)
            ts.khoan_hien_tai = khoan
            continue

        # dong noi tiep
        if ts.khoan_hien_tai:
            ts.buffer_dong.append(line)
        elif ts.dieu_hien_tai:
            ts.buffer_dong.append(line)
        # con lai: thuoc phan dau van ban (bo qua, tru can cu da trich rieng)

    _flush_buffer_vao_khoan(ts)
    _flush_buffer_vao_dieu(ts)

    # sinh noi dung day du cho Dieu: tieu_de + cac Khoan
    for d in dieu_list:
        if d.khoan:
            cac_khoan: list[str] = []
            for k in d.khoan:
                prefix = f"{k.so_khoan}."
                if k.diem:
                    prefix = f"{k.diem})"
                cac_khoan.append(f"{prefix} {k.noi_dung}".strip())
            parts: list[str] = []
            if d.tieu_de:
                parts.append(d.tieu_de)
            parts.extend(cac_khoan)
            if not d.noi_dung:
                d.noi_dung = "\n".join(parts).strip()
            else:
                d.noi_dung = (d.noi_dung + "\n" + "\n".join(cac_khoan)).strip()
        else:
            if d.tieu_de and not d.noi_dung:
                d.noi_dung = d.tieu_de

    can_cu_tho = _trich_can_cu(lines)

    # cap nhat co van ban sua doi
    la_sua_doi = _la_van_ban_sua_doi(meta.ten, dieu_list)
    if la_sua_doi and not meta.la_van_ban_sua_doi:
        meta = meta.model_copy(update={"la_van_ban_sua_doi": True})

    return VanBanParsed(
        meta=meta,
        can_cu_tho=can_cu_tho,
        dieu=dieu_list,
        canh_bao=canh_bao,
    )

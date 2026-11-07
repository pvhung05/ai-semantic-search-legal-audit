"""Segment du thao thanh don vi (dieu|khoan|diem|cum|doan).

Co Dieu  -> dieu + khoan + diem (nhu parser luat).
Khong Dieu -> ^[IVX]+\\., ^\\d+\\., ^[a-zđ]\\) -> doan.
> 30 doan   -> LLM gom thanh cum (JSON [{ten, don_vi_ids}]).

hash = sha256(normalize(noi_dung) | tieu_de cap tren).
Trich can_cu_tho (de parent_docs).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.doisanh.ingestion.normalize import chuan_hoa_so_sanh, chuan_hoa_text
from app.doisanh.ingestion.parser import (
    RE_CHUONG, RE_DIEM, RE_DIEU, RE_KHOAN, RE_MUC, _trich_can_cu,
)

RE_LA_MA = re.compile(r"^[IVX]+\.\s+(.*)$")
RE_SO_CHAM = re.compile(r"^\d+\.\s+(.*)$")
RE_CHU_NGOAC = re.compile(r"^[a-zđ]\)\s+(.*)$")
RE_VE_HEADER = re.compile(r"^Về\s+[A-ZĐa-zđàáạảâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]")
RE_CAU = re.compile(r"(?<=[\.;!?])\s+(?=[A-ZĐa-zđ0-9\"])")

# Boilerplate quoc hieu/tieu ngu/dia danh-ngay o block ky -> bo qua khi segment.
RE_QUOC_HIEU = re.compile(r"CỘNG\s*HO[ÀA]\s*XÃ\s*HỘI\s*CHỦ\s*NGHĨA\s*VIỆT\s*NAM", re.I)
RE_TIEU_NGU = re.compile(r"Độc\s*lập\s*-\s*Tự\s*do\s*-\s*Hạnh\s*phúc", re.I)
RE_DIA_DANH_NGAY = re.compile(r"^[^,\n]{1,30},\s*ngày\b.*\bnăm\b", re.I)


def _la_boilerplate(line: str) -> bool:
    """Dong quoc hieu / tieu ngu / 'dia danh, ngay ... thang ... nam' (khong phai noi dung)."""
    return bool(
        RE_QUOC_HIEU.search(line)
        or RE_TIEU_NGU.search(line)
        or RE_DIA_DANH_NGAY.match(line)
    )


@dataclass
class DonViSegment:
    id: str
    cap: str
    noi_dung: str
    hash: str
    thu_tu: int
    parent_id: str | None = None
    chuong: str | None = None
    so_dieu: str | None = None
    so_khoan: str | None = None
    diem: str | None = None
    tieu_de: str | None = None


@dataclass
class KetQuaSegment:
    don_vi: list[DonViSegment] = field(default_factory=list)
    can_cu_tho: list[str] = field(default_factory=list)
    co_cau_truc_dieu: bool = False


def _hash(noi_dung: str, tieu_de_tren: str | None) -> str:
    key = chuan_hoa_so_sanh(noi_dung) + "|" + (tieu_de_tren or "")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def segment_du_thao(text: str, tai_lieu_id: str) -> KetQuaSegment:
    text = chuan_hoa_text(text)
    lines = text.split("\n")
    kq = KetQuaSegment()
    kq.can_cu_tho = _trich_can_cu(lines)

    # Phat hien co cau truc Dieu khong
    co_dieu = any(RE_DIEU.match(ln.strip()) for ln in lines)
    kq.co_cau_truc_dieu = co_dieu

    if co_dieu:
        _segment_co_dieu(lines, tai_lieu_id, kq)
    else:
        _segment_khong_dieu(lines, tai_lieu_id, kq)
    return kq


def _segment_co_dieu(lines: list[str], tai_lieu_id: str, kq: KetQuaSegment) -> None:
    """Tach Dieu + Khoan + Diem.

    Dieu: KHONG tao chunk doc lap, chi dong vai 'tieu de cap tren' cho Khoan/Diem.
    Khoan/Diem: moi don vi la 1 chunk, text embed = '<tieu_de_dieu>. <noi_dung>'.
    id gan '#<thu_tu>' de duy nhat khi du thao lap so Dieu/Khoan (vd trich nguyen van khoan luat).
    """
    chuong_hien_tai: str | None = None
    tieu_de_dieu_hien_tai: str | None = None
    so_dieu_hien_tai: str | None = None
    dieu_id_hien_tai: str | None = None
    cur_khoan: DonViSegment | None = None
    co_khoan_trong_dieu: bool = False
    thu_tu = 0
    noi_dung_tam: list[str] = []

    def _flush_vao_khoan() -> None:
        # Chi gom vao Khoan hien tai neu dang trong Khoan.
        # Neu dang o Dieu khong Khoan, giu nguyen noi_dung_tam de flush sau.
        if cur_khoan is None:
            return
        if noi_dung_tam:
            them = " ".join(noi_dung_tam).strip()
            if them:
                cur_khoan.noi_dung = (cur_khoan.noi_dung + " " + them).strip()
            noi_dung_tam.clear()

    def _flush_dieu_khong_khoan() -> None:
        """Dieu khong co Khoan -> tao 1 chunk cap 'khoan' ngam (so_khoan=None)."""
        nonlocal thu_tu
        if not noi_dung_tam or co_khoan_trong_dieu or not so_dieu_hien_tai:
            noi_dung_tam.clear()
            return
        noi_dung = " ".join(noi_dung_tam).strip()
        noi_dung_tam.clear()
        if not noi_dung:
            return
        thu_tu += 1
        dv = DonViSegment(
            id=f"{dieu_id_hien_tai}:K0#{thu_tu}",
            cap="khoan", chuong=chuong_hien_tai, so_dieu=so_dieu_hien_tai, so_khoan=None,
            tieu_de=tieu_de_dieu_hien_tai,
            noi_dung=noi_dung, hash="", thu_tu=thu_tu,
            parent_id=None,
        )
        kq.don_vi.append(dv)

    def _reset_dieu() -> None:
        nonlocal so_dieu_hien_tai, dieu_id_hien_tai, tieu_de_dieu_hien_tai
        nonlocal cur_khoan, co_khoan_trong_dieu
        so_dieu_hien_tai = dieu_id_hien_tai = tieu_de_dieu_hien_tai = None
        cur_khoan = None
        co_khoan_trong_dieu = False

    for raw in lines:
        line = raw.strip()
        if not line:
            _flush_vao_khoan()
            # Dong trong sau mot Dieu CHUA co than (Dieu one-liner cua QUYET DINH, hoac khoi
            # tieu de "QUY CHE ... (Ban hanh kem theo ...)") -> dong Dieu do, tranh gan nham
            # phan sau vao so_dieu cu.
            # shortcut: gia dinh VBQPPL khong chen dong trong GIUA tieu de Dieu va than/Khoan
            #           dau tien cua no; neu VB co -> bo dieu kien nay.
            if cur_khoan is None and not noi_dung_tam and so_dieu_hien_tai:
                so_dieu_hien_tai = dieu_id_hien_tai = tieu_de_dieu_hien_tai = None
            continue
        if _la_boilerplate(line):
            continue
        # Chuong/Muc: KHONG tao chunk, chi lam ngu canh. Flush noi dung dang gom (thuoc
        # Khoan/Dieu truoc) roi reset ngu canh Dieu -> tieu de chuong/muc o DONG KE TIEP
        # (vi du 'Chuong III' / 'TIEP NHAN, XU LY DON') bi bo, khong thanh don vi rac.
        m = RE_CHUONG.match(line)
        if m:
            if cur_khoan:
                _flush_vao_khoan()
            else:
                _flush_dieu_khong_khoan()
            chuong_hien_tai = m.group(1)
            _reset_dieu()
            continue
        if RE_MUC.match(line):
            if cur_khoan:
                _flush_vao_khoan()
            else:
                _flush_dieu_khong_khoan()
            _reset_dieu()
            continue
        m = RE_DIEU.match(line)
        if m:
            # Flush noi dung tich luy: hoac vao Khoan hien tai, hoac tao chunk Dieu-khong-Khoan
            if cur_khoan:
                _flush_vao_khoan()
            else:
                _flush_dieu_khong_khoan()
            so_dieu_hien_tai = m.group(1)
            tieu_de_dieu_hien_tai = (m.group(2) or "").strip() or None
            dieu_id_hien_tai = f"{tai_lieu_id}:D{so_dieu_hien_tai}"
            cur_khoan = None
            co_khoan_trong_dieu = False
            continue
        m = RE_KHOAN.match(line)
        if m and so_dieu_hien_tai:
            _flush_vao_khoan()
            co_khoan_trong_dieu = True
            thu_tu += 1
            so_khoan = m.group(1)
            noi_dung = (m.group(2) or "").strip()
            cur_khoan = DonViSegment(
                id=f"{dieu_id_hien_tai}:K{so_khoan}#{thu_tu}",
                cap="khoan", chuong=chuong_hien_tai, so_dieu=so_dieu_hien_tai, so_khoan=so_khoan,
                tieu_de=tieu_de_dieu_hien_tai,
                noi_dung=noi_dung, hash="", thu_tu=thu_tu,
                parent_id=None,
            )
            kq.don_vi.append(cur_khoan)
            continue
        m = RE_DIEM.match(line)
        if m and cur_khoan:
            _flush_vao_khoan()
            thu_tu += 1
            diem = m.group(1)
            noi_dung = (m.group(2) or "").strip()
            # Diem chunk rieng, tieu_de = noi_dung Khoan cha (lam context khi embed)
            diem_dv = DonViSegment(
                id=f"{cur_khoan.id}:D{diem}#{thu_tu}",
                cap="diem", chuong=chuong_hien_tai, so_dieu=so_dieu_hien_tai, so_khoan=cur_khoan.so_khoan,
                diem=diem, tieu_de=cur_khoan.noi_dung,
                noi_dung=noi_dung, hash="", thu_tu=thu_tu,
                parent_id=cur_khoan.id,
            )
            kq.don_vi.append(diem_dv)
            continue
        noi_dung_tam.append(line)
    # Ket thuc: flush not luu vao Khoan hien tai, hoac tao chunk Dieu-khong-Khoan cuoi cung
    if cur_khoan:
        _flush_vao_khoan()
    else:
        _flush_dieu_khong_khoan()

    for dv in kq.don_vi:
        dv.hash = _hash(dv.noi_dung, dv.tieu_de)


def _segment_khong_dieu(lines: list[str], tai_lieu_id: str, kq: KetQuaSegment) -> None:
    """Segment van xuoi/de muc:

    1. Dong `^[IVX]+\\. <TIEU DE>` hoac `^Ve <X>` -> KHONG tao chunk, chi set tieu_de muc.
    2. Dong `^N. <noi dung>` hoac `^a) <noi dung>` -> 1 chunk doan voi tieu_de=tieu de muc.
    3. Paragraph khong co pattern trong muc hien tai -> split cau -> moi cau 1 chunk.
    """
    thu_tu = 0
    muc_tieu_de: str | None = None
    buffer_paragraph: list[str] = []

    def _flush_paragraph() -> None:
        nonlocal thu_tu, buffer_paragraph
        if not buffer_paragraph:
            return
        para = " ".join(buffer_paragraph).strip()
        buffer_paragraph = []
        if muc_tieu_de is None or not para:
            return
        cau_list = [c.strip() for c in RE_CAU.split(para) if c.strip()]
        for cau in cau_list:
            thu_tu += 1
            dv = DonViSegment(
                id=f"{tai_lieu_id}:P{thu_tu}",
                cap="doan", tieu_de=muc_tieu_de, noi_dung=cau,
                hash=_hash(cau, muc_tieu_de),
                thu_tu=thu_tu,
            )
            kq.don_vi.append(dv)

    for raw in lines:
        line = raw.strip()
        if not line:
            _flush_paragraph()
            continue
        if _la_boilerplate(line):
            continue
        m = RE_LA_MA.match(line)
        if m:
            _flush_paragraph()
            muc_tieu_de = (m.group(1) or line).strip() or line
            continue
        if RE_VE_HEADER.match(line):
            _flush_paragraph()
            muc_tieu_de = line
            continue
        m = RE_SO_CHAM.match(line)
        if m:
            _flush_paragraph()
            thu_tu += 1
            noi_dung = (m.group(1) or line).strip()
            dv = DonViSegment(
                id=f"{tai_lieu_id}:P{thu_tu}",
                cap="doan", tieu_de=muc_tieu_de, noi_dung=noi_dung,
                hash=_hash(noi_dung, muc_tieu_de),
                thu_tu=thu_tu,
            )
            kq.don_vi.append(dv)
            continue
        m = RE_CHU_NGOAC.match(line)
        if m:
            _flush_paragraph()
            thu_tu += 1
            noi_dung = (m.group(1) or line).strip()
            dv = DonViSegment(
                id=f"{tai_lieu_id}:P{thu_tu}",
                cap="doan", tieu_de=muc_tieu_de, noi_dung=noi_dung,
                hash=_hash(noi_dung, muc_tieu_de),
                thu_tu=thu_tu,
            )
            kq.don_vi.append(dv)
            continue
        buffer_paragraph.append(line)
    _flush_paragraph()


def gop_thanh_cum(
    don_vi: list[DonViSegment], goi_json_fn, tai_lieu_id: str, nguong: int = 30,
) -> list[DonViSegment]:
    """Khi > nguong doan -> LLM gom nhom. Tra DonViSegment cap 'cum'."""
    if len(don_vi) <= nguong:
        return []
    payload = [{"id": dv.id, "noi_dung": dv.noi_dung[:200]} for dv in don_vi]
    messages = [
        {"role": "system", "content": "Ban la chuyen vien tham dinh. Chi tra JSON."},
        {"role": "user", "content": (
            "Gom cac doan sau thanh cum chu de. Tra JSON mang "
            "[{ten, don_vi_ids:[...]}]. Danh sach:\n" + str(payload)
        )},
    ]
    data = goi_json_fn(messages)
    cum: list[DonViSegment] = []
    thu_tu = max(dv.thu_tu for dv in don_vi) + 1
    for i, item in enumerate(data if isinstance(data, list) else []):
        ten = item.get("ten", f"Cum {i + 1}")
        ids = item.get("don_vi_ids", [])
        noi_dung = " ".join(dv.noi_dung for dv in don_vi if dv.id in set(ids))
        cum.append(DonViSegment(
            id=f"{tai_lieu_id}:C{i + 1}",
            cap="cum", tieu_de=ten, noi_dung=noi_dung,
            hash=_hash(noi_dung, ten), thu_tu=thu_tu + i,
        ))
    return cum

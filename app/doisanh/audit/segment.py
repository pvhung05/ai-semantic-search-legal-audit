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
    RE_CAN_CU, RE_CHUONG, RE_DIEM, RE_DIEU, RE_KHOAN, RE_MUC, _trich_can_cu,
)

# Dong tieu de loai van ban (de nhan dien khoi trich yeu = chu de chung cua ca van ban).
RE_LOAI_VB = re.compile(
    r"^(NGHỊ QUYẾT|QUYẾT ĐỊNH|NGHỊ ĐỊNH|THÔNG TƯ|QUY CHẾ|QUY ĐỊNH|QUY TRÌNH|CHỈ THỊ|"
    r"KẾ HOẠCH|LUẬT|PHÁP LỆNH|HIẾN PHÁP|ĐỀ ÁN)\b", re.IGNORECASE)

RE_LA_MA = re.compile(r"^[IVX]+\.\s+(.*)$")
RE_SO_CHAM = re.compile(r"^\d+\.\s+(.*)$")
RE_CHU_NGOAC = re.compile(r"^[a-zđ]\)\s+(.*)$")
RE_VE_HEADER = re.compile(r"^Về\s+[A-ZĐa-zđàáạảâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]")
RE_CAU = re.compile(r"(?<=[\.;!?])\s+(?=[A-ZĐa-zđ0-9\"])")

# Boilerplate quoc hieu/tieu ngu/dia danh-ngay o block ky -> bo qua khi segment.
# H[OÒ][ÀA]? khop ca 'HÒA' (dau o O) lan 'HOÀ'/'HOA' (dau o A) - 2 cach bo dau tieng Viet.
RE_QUOC_HIEU = re.compile(r"CỘNG\s*H[OÒ][ÀA]?\s*XÃ\s*HỘI\s*CHỦ\s*NGHĨA\s*VIỆT\s*NAM", re.I)
RE_TIEU_NGU = re.compile(r"Độc\s*lập\s*-\s*Tự\s*do\s*-\s*Hạnh\s*phúc", re.I)
RE_DIA_DANH_NGAY = re.compile(r"^[^,\n]{1,30},\s*ngày\b.*\bnăm\b", re.I)
# Co quan ban hanh / chuc danh nguoi ky o block ky cuoi VB - dong CHU HOA dung rieng.
# CO Y khong IGNORECASE: noi dung thuong viet thuong ('Chu tich UBND xa co trach nhiem...') nen
# chi khop dang CHU HOA cua block ky, tranh nuot noi dung that.
RE_CO_QUAN_KY = re.compile(
    r"^(TÒA ÁN NHÂN DÂN|VIỆN KIỂM SÁT NHÂN DÂN|ỦY BAN NHÂN DÂN|HỘI ĐỒNG NHÂN DÂN|CHÍNH PHỦ"
    r"|QUỐC HỘI|BỘ [A-ZÀ-Ỹ]|CHÁNH ÁN|PHÓ CHÁNH ÁN|BỘ TRƯỞNG|THỦ TƯỚNG|CHỦ TỊCH|PHÓ CHỦ TỊCH"
    r"|TỈNH\b|THÀNH PHỐ\b|KT\.|TM\.|TL\.|NƠI NHẬN)"
)
# Them cho block ky: dong phan cach '____', so hieu VB du thao 'Số: .../2026/QĐ-UBND'.
RE_DAU_PHAN_CACH = re.compile(r"^[_\-–—]{3,}\s*$")
RE_SO_HIEU_KY = re.compile(r"^Số:\s*\S*\s*/\s*\d{4}\s*/")
# Tieu de van ban con (phu luc) 'Ban hanh kem theo / Kem theo Quyet dinh so ...' -> ranh gioi.
RE_KEM_THEO = re.compile(r"^\(?\s*(Ban hành kèm theo|Kèm theo)\b", re.I)
# Khoi 'Noi nhan:' o cuoi VB -> tu day tro di la danh sach nhan + chu ky, bo qua.
RE_NOI_NHAN = re.compile(r"^Nơi\s*nhận\s*:", re.I)


def _la_boilerplate(line: str) -> bool:
    """Dong quoc hieu / tieu ngu / 'dia danh, ngay...' / co quan ban hanh - nguoi ky / phan cach / so hieu."""
    return bool(
        RE_QUOC_HIEU.search(line)
        or RE_TIEU_NGU.search(line)
        or RE_DIA_DANH_NGAY.match(line)
        or RE_CO_QUAN_KY.match(line)
        or RE_DAU_PHAN_CACH.match(line)
        or RE_SO_HIEU_KY.match(line)
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
    trich_yeu: str = ""   # chu de chung cua ca van ban (de gui kem prompt xac dinh linh vuc)


def _trich_yeu(lines: list[str]) -> str:
    """Trich yeu = chu de chung cua van ban: tu dong tieu de loai VB (QUYET DINH/QUY CHE...) +
    cac dong ngay sau, dung truoc 'Can cu'/Chuong/Muc/Dieu hoac dong trong. Rong neu khong nhan dien."""
    out: list[str] = []
    bat_dau = False
    for raw in lines:
        line = raw.strip()
        if not line or _la_boilerplate(line):
            if bat_dau:
                break
            continue
        if not bat_dau:
            if RE_LOAI_VB.match(line):
                bat_dau = True
                out.append(line)
            continue
        if (RE_CAN_CU.match(line) or RE_DIEU.match(line) or RE_CHUONG.match(line)
                or RE_MUC.match(line)):
            break
        out.append(line)
        if len(out) >= 5:
            break
    return " ".join(out).strip()


def _hash(noi_dung: str, tieu_de_tren: str | None) -> str:
    key = chuan_hoa_so_sanh(noi_dung) + "|" + (tieu_de_tren or "")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def segment_du_thao(text: str, tai_lieu_id: str) -> KetQuaSegment:
    text = chuan_hoa_text(text)
    lines = text.split("\n")
    kq = KetQuaSegment()
    kq.can_cu_tho = _trich_can_cu(lines)
    kq.trich_yeu = _trich_yeu(lines)

    # Phat hien co cau truc Dieu khong
    co_dieu = any(RE_DIEU.match(ln.strip()) for ln in lines)
    kq.co_cau_truc_dieu = co_dieu

    if co_dieu:
        _segment_co_dieu(lines, tai_lieu_id, kq)
    else:
        _segment_khong_dieu(lines, tai_lieu_id, kq)
    return kq


# Khoan co Diem ma tong do dai (Khoan + cac Diem) < nguong nay (so TU) -> gop thanh 1 don vi
# thay vi tach tung Diem -> giam so don vi du thao -> giam so lan goi LLM tier2.
# shortcut: dem theo TU (split khoang trang); doi sang len(text) neu muon tinh ky tu.
NGUONG_GOP_DIEM_TU = 300


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
    cur_diems: list[DonViSegment] = []   # buffer Diem cua Khoan hien tai (chot khi het Khoan)
    cur_diem: DonViSegment | None = None  # Diem dang mo -> noi dung tiep sau ('+' bullet, doan) gom vao day
    co_khoan_trong_dieu: bool = False
    thu_tu = 0
    noi_dung_tam: list[str] = []
    bo_qua_ky = False   # True sau khi gap 'Noi nhan:' -> bo qua block ky den Chuong/Dieu ke tiep

    def _flush_vao_khoan() -> None:
        # Gom noi_dung_tam vao DIEM dang mo (de '+' bullet / doan giai thich thuoc dung Diem);
        # neu khong trong Diem thi vao Khoan. Dieu-khong-Khoan: giu nguyen de flush sau.
        target = cur_diem or cur_khoan
        if target is None:
            return
        if noi_dung_tam:
            them = " ".join(noi_dung_tam).strip()
            if them:
                target.noi_dung = (target.noi_dung + " " + them).strip()
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

    def _chot_khoan() -> None:
        """Ket thuc Khoan hien tai. Neu tong (Khoan + cac Diem) < NGUONG_GOP_DIEM_TU tu -> GOP
        Diem vao Khoan thanh 1 don vi (giam so lan goi LLM); nguoc lai giu Khoan + tung Diem rieng."""
        nonlocal cur_khoan, cur_diems, cur_diem
        if cur_khoan is None:
            cur_diems = []
            cur_diem = None
            return
        _flush_vao_khoan()
        cur_diem = None
        if cur_diems:
            gop = cur_khoan.noi_dung + " " + " ".join(
                f"{d.diem}) {d.noi_dung}" for d in cur_diems)
            if len(gop.split()) < NGUONG_GOP_DIEM_TU:
                cur_khoan.noi_dung = gop.strip()
                kq.don_vi.append(cur_khoan)        # gop: chi 1 don vi Khoan
            else:
                kq.don_vi.append(cur_khoan)        # dai: giu Khoan + tung Diem rieng
                kq.don_vi.extend(cur_diems)
        else:
            kq.don_vi.append(cur_khoan)
        cur_khoan = None
        cur_diems = []

    def _reset_dieu() -> None:
        nonlocal so_dieu_hien_tai, dieu_id_hien_tai, tieu_de_dieu_hien_tai
        nonlocal cur_khoan, co_khoan_trong_dieu, cur_diem
        so_dieu_hien_tai = dieu_id_hien_tai = tieu_de_dieu_hien_tai = None
        cur_khoan = None
        cur_diem = None
        co_khoan_trong_dieu = False

    for raw in lines:
        line = raw.strip()
        # Dang trong block ky (sau 'Noi nhan:') -> bo qua, tru khi gap van ban con moi (Chuong/Dieu).
        if bo_qua_ky:
            if RE_CHUONG.match(line) or RE_DIEU.match(line):
                bo_qua_ky = False
            else:
                continue
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
        # 'Noi nhan:' -> bat dau block ky cuoi VB: chot don vi dang mo roi bo qua phan con lai.
        if RE_NOI_NHAN.match(line):
            if cur_khoan:
                _chot_khoan()
            else:
                _flush_dieu_khong_khoan()
            _reset_dieu()
            bo_qua_ky = True
            continue
        # Chuong/Muc: KHONG tao chunk, chi lam ngu canh. Flush noi dung dang gom (thuoc
        # Khoan/Dieu truoc) roi reset ngu canh Dieu -> tieu de chuong/muc o DONG KE TIEP
        # (vi du 'Chuong III' / 'TIEP NHAN, XU LY DON') bi bo, khong thanh don vi rac.
        m = RE_CHUONG.match(line)
        if m:
            if cur_khoan:
                _chot_khoan()
            else:
                _flush_dieu_khong_khoan()
            chuong_hien_tai = m.group(1)
            _reset_dieu()
            continue
        if RE_MUC.match(line):
            if cur_khoan:
                _chot_khoan()
            else:
                _flush_dieu_khong_khoan()
            _reset_dieu()
            continue
        m = RE_DIEU.match(line)
        if m:
            # Chot Khoan truoc (gop/tach Diem); hoac tao chunk Dieu-khong-Khoan
            if cur_khoan:
                _chot_khoan()
            else:
                _flush_dieu_khong_khoan()
            so_dieu_hien_tai = m.group(1)
            tieu_de_dieu_hien_tai = (m.group(2) or "").strip() or None
            dieu_id_hien_tai = f"{tai_lieu_id}:D{so_dieu_hien_tai}"
            cur_khoan = None
            cur_diem = None
            co_khoan_trong_dieu = False
            continue
        # Tieu de van ban con (phu luc 'Ban hanh kem theo Quyet dinh...') -> ranh gioi:
        # reset ngu canh Dieu + BO khoi tieu de dang gom (tranh dinh vao Dieu truoc do).
        if RE_KEM_THEO.match(line):
            if cur_khoan:
                _chot_khoan()
            _reset_dieu()
            noi_dung_tam.clear()
            continue
        m = RE_KHOAN.match(line)
        if m and so_dieu_hien_tai:
            _chot_khoan()           # chot Khoan truoc (gop/tach Diem) truoc khi mo Khoan moi
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
            cur_diems = []          # buffer Diem cua Khoan moi; chot khi het Khoan
            cur_diem = None         # chua vao Diem nao -> noi dung tiep theo vao than Khoan
            continue
        m = RE_DIEM.match(line)
        if m and cur_khoan:
            _flush_vao_khoan()      # flush phan truoc vao Diem truoc (hoac than Khoan neu la Diem dau)
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
            cur_diems.append(diem_dv)   # buffer; _chot_khoan quyet dinh gop hay tach
            cur_diem = diem_dv          # noi dung tiep sau ('+' bullet, doan) gom vao Diem nay
            continue
        noi_dung_tam.append(line)
    # Ket thuc: chot Khoan cuoi (gop/tach Diem), hoac tao chunk Dieu-khong-Khoan cuoi
    if cur_khoan:
        _chot_khoan()
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
        if not para:
            return
        tieu_de = muc_tieu_de or "Nội dung"
        cau_list = [c.strip() for c in RE_CAU.split(para) if c.strip()]
        for cau in cau_list:
            thu_tu += 1
            dv = DonViSegment(
                id=f"{tai_lieu_id}:P{thu_tu}",
                cap="doan", tieu_de=tieu_de, noi_dung=cau,
                hash=_hash(cau, tieu_de),
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

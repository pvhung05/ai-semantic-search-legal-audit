# Ví dụ: tier1 viết theo Open/Closed và Dependency Inversion

```python
# app/audit/tier1/base.py
from __future__ import annotations
from datetime import date
from typing import Protocol
from app.models.schemas import DonVi, PhatHien

class HieuLucReader(Protocol):
    def khoan_hieu_luc_tai(self, van_ban_id: str, so_dieu: str, so_khoan: str | None,
                           diem: str | None, ngay: date) -> Khoan | None: ...
    def tim_van_ban(self, so_hieu: str | None, ten: str | None) -> VanBan | None: ...

class Checker(Protocol):
    """Một kiểm tra xác định trên một đơn vị dự thảo."""
    def kiem_tra(self, don_vi: DonVi, ngay: date) -> list[PhatHien]: ...
```

```python
# app/audit/tier1/checks/dan_chieu.py
class KiemTraDanChieu:
    def __init__(self, reader: HieuLucReader, parser: CitationParser) -> None:
        self._reader = reader
        self._parser = parser

    def kiem_tra(self, don_vi: DonVi, ngay: date) -> list[PhatHien]:
        return [ph for dc in self._parser.parse(don_vi.noi_dung)
                   if (ph := self._danh_gia(dc, don_vi, ngay))]

    def _danh_gia(self, dc: DanChieu, don_vi: DonVi, ngay: date) -> PhatHien | None:
        vb = self._reader.tim_van_ban(dc.so_hieu, dc.ten_van_ban)
        if vb is None:
            return PhatHien.tang1(don_vi, LoaiLoi.DAN_CHIEU_SAI_SO_HIEU, doan=dc.text_dan,
                                  giai_thich="Không tìm thấy văn bản được dẫn trong kho")
        khoan = self._reader.khoan_hieu_luc_tai(vb.id, dc.so_dieu, dc.so_khoan, dc.diem, ngay)
        if khoan is None:
            return self._phat_hien_khong_hieu_luc(vb, dc, don_vi, ngay)
        return None
```

```python
# app/audit/tier1/__init__.py  – lắp ráp
def tao_tier1(reader: HieuLucReader, nguong_diff: float) -> "Tier1":
    checks: list[Checker] = [
        KiemTraDanChieu(reader, CitationParser()),
        KiemTraNguyenVan(reader, nguong_diff),
        KiemTraTheThuc(reader),
    ]
    return Tier1(checks)

class Tier1:
    def __init__(self, checks: list[Checker]) -> None:
        self._checks = checks
    def chay(self, don_vis: list[DonVi], ngay: date) -> list[PhatHien]:
        return [ph for dv in don_vis for c in self._checks for ph in c.kiem_tra(dv, ngay)]
```

```python
# tests/audit/test_tier1_dan_chieu.py
def test_dan_khoan_da_bai_bo_bao_dan_bi_bai_bo(mem_repo):
    mem_repo.them_khoan("ND-2021-01", "58", "4", trang_thai="bai_bo", hieu_luc_den=date(2026, 2, 28))
    check = KiemTraDanChieu(mem_repo, CitationParser())
    dv = DonVi.khoan("TL-1:D5:K2", "theo khoản 4 Điều 58 Nghị định 01/2021/NĐ-CP ...")
    ph = check.kiem_tra(dv, date(2026, 6, 1))
    assert [p.loai_loi for p in ph] == [LoaiLoi.DAN_BI_BAI_BO]
```

Điểm cần thấy: thêm loại kiểm tra mới = thêm một lớp vào `checks/` và một dòng trong `tao_tier1`; test không cần DB thật; `Tier1` không biết gì về SQL hay LLM.

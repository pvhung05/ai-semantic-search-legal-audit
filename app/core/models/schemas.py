"""Pydantic models dung chung cho ingestion, audit, API."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

LoaiVanBan = Literal[
    "hien_phap", "bo_luat", "luat", "nghi_quyet",
    "nghi_dinh", "quyet_dinh", "thong_tu", "khac",
]
TrangThaiVanBan = Literal[
    "chua_hieu_luc", "con_hieu_luc", "het_hieu_luc_mot_phan", "het_hieu_luc",
]
TrangThaiDieu = Literal[
    "con_hieu_luc", "het_hieu_luc", "bai_bo", "chua_hieu_luc",
]
TinCay = Literal["xac_nhan", "can_ra_soat"]


class VanBanMeta(BaseModel):
    """Metadata cua mot van ban khi upload."""
    id: str
    so_hieu: str
    ten: str
    loai: LoaiVanBan
    cap: int
    co_quan_ban_hanh: Optional[str] = None
    ngay_ban_hanh: Optional[date] = None
    ngay_hieu_luc: Optional[date] = None
    ngay_het_hieu_luc: Optional[date] = None
    linh_vuc: list[str] = Field(default_factory=list)
    la_van_ban_sua_doi: bool = False
    tin_cay: TinCay = "can_ra_soat"
    nguon_file: Optional[str] = None


class Khoan(BaseModel):
    """Mot Khoan hoac Diem trong mot Dieu."""
    so_khoan: str
    diem: Optional[str] = None
    noi_dung: str
    thu_tu: int
    parent_so_khoan: Optional[str] = None


class Dieu(BaseModel):
    """Mot Dieu luat sau khi parse."""
    so_dieu: str
    so_dieu_num: int
    tieu_de: Optional[str] = None
    noi_dung: str
    thu_tu: int
    chuong_so: Optional[str] = None
    chuong_ten: Optional[str] = None
    muc_so: Optional[str] = None
    muc_ten: Optional[str] = None
    khoan: list[Khoan] = Field(default_factory=list)
    tom_tat: Optional[str] = None


class VanBanParsed(BaseModel):
    """Toan bo ket qua parse mot file luat."""
    meta: VanBanMeta
    can_cu_tho: list[str] = Field(default_factory=list)
    dieu: list[Dieu] = Field(default_factory=list)
    canh_bao: list[str] = Field(default_factory=list)


LoaiLenh = Literal["sua_doi", "bo_sung", "bai_bo", "thay_cum_tu"]


class LenhSuaDoi(BaseModel):
    """Mot lenh sua doi/bo sung/bai bo rut ra tu van ban sua doi."""
    loai: LoaiLenh
    dich_so_hieu: Optional[str] = None
    dich_van_ban_id: Optional[str] = None
    dich_so_dieu: Optional[str] = None
    dich_so_khoan: Optional[str] = None
    dich_diem: Optional[str] = None
    vi_tri: Optional[Literal["sau", "truoc"]] = None
    noi_dung_moi: Optional[str] = None
    cum_tu_cu: Optional[str] = None
    cum_tu_moi: Optional[str] = None
    ngay_hieu_luc: Optional[date] = None
    nguon_lenh: Optional[str] = None
    tin_cay: TinCay = "can_ra_soat"


class DanChieu(BaseModel):
    """Mot dan chieu phap ly rut ra tu text."""
    text_dan: str
    so_hieu: Optional[str] = None
    ten_van_ban: Optional[str] = None
    so_dieu: Optional[str] = None
    so_khoan: Optional[str] = None
    diem: Optional[str] = None
    la_noi_bo: bool = False


class DonVi(BaseModel):
    """Mot don vi cua tai lieu du thao sau segment."""
    id: str
    cap: Literal["dieu", "khoan", "diem", "cum", "doan"]
    so_dieu: Optional[str] = None
    so_khoan: Optional[str] = None
    diem: Optional[str] = None
    tieu_de: Optional[str] = None
    noi_dung: str
    hash: str
    thu_tu: int
    parent_id: Optional[str] = None


class AnhXa(BaseModel):
    """Anh xa mot Dieu du thao sang cac Dieu me."""
    don_vi_id: str
    dieu_me_ids: list[str] = Field(default_factory=list)
    loai: Literal["cu_the_hoa", "dan_chieu", "cung_chu_de", "khong"]
    tin_cay: float = 0.0


LoaiLoi = Literal[
    "dan_chieu_khong_ton_tai", "dan_chieu_sai_so_hieu",
    "dan_het_hieu_luc", "dan_bi_bai_bo", "dan_chua_hieu_luc",
    "trich_sai_nguyen_van", "the_thuc",
    "thu_hep_pham_vi", "mo_rong_pham_vi", "them_dieu_kien", "them_nghia_vu",
    "doi_so_lieu", "dat_thu_tuc_moi", "mau_thuan_truc_tiep", "vuot_tham_quyen",
    "khong_co_can_cu_uy_quyen", "phu_hop",
]
MucDo = Literal["cao", "trung_binh", "thap"]


class CanCu(BaseModel):
    dieu_me_id: Optional[str] = None
    van_ban_id: Optional[str] = None
    so_khoan: Optional[str] = None
    diem: Optional[str] = None
    trich_dan: Optional[str] = None


class PhatHien(BaseModel):
    """Mot phat hien doi chieu."""
    don_vi_id: str
    tang: Literal[1, 2, 3]
    loai_loi: LoaiLoi
    muc_do: MucDo
    tin_cay: float = 0.0
    anh_xa_id: Optional[int] = None
    can_cu: Optional[CanCu] = None
    doan_du_thao: Optional[str] = None
    giai_thich: Optional[str] = None
    de_xuat_sua: Optional[str] = None

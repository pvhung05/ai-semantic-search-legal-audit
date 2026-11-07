"""Prompt system cho mapping va tier2.

Tieng Viet, vai tro 'chuyen vien tham dinh van ban', chi tra JSON.
"""
from __future__ import annotations

HE_THONG_CHUNG = (
    "Ban la chuyen vien tham dinh van ban quy pham phap luat Viet Nam. "
    "Chi tra JSON thuan tuy, khong dung markdown fence, khong giai thich ngoai JSON."
)

MAPPING_HE_THONG = HE_THONG_CHUNG + (
    " Nhiem vu: anh xa moi Dieu/cum cua du thao sang 0..N Dieu cua van ban me."
)


def prompt_mapping(muc_luc_du_thao: list[dict], muc_luc_me: list[dict], max_dieu_me: int) -> list[dict[str, str]]:
    """Dung mapping Dieu du thao <-> Dieu me."""
    return [
        {"role": "system", "content": MAPPING_HE_THONG},
        {"role": "user", "content": (
            "DAU VAO 1 - Du thao (moi phan tu la MOT Dieu cua du thao can tim Dieu me):\n"
            + str(muc_luc_du_thao) + "\n\n"
            "DAU VAO 2 - Van ban me (moi phan tu la MOT Dieu me co san):\n"
            + str(muc_luc_me) + "\n\n"
            "NHIEM VU: Voi MOI Dieu trong DAU VAO 1, tim toi da "
            f"{max_dieu_me} Dieu me gan nhat trong DAU VAO 2.\n\n"
            "DINH DANG TRA LOI (CHI JSON mang, KHONG markdown):\n"
            '[{"don_vi_id": "<id Dieu du thao, lay tu DAU VAO 1>",'
            ' "dieu_me_ids": ["<dieu_id tu DAU VAO 2>", ...],'
            ' "loai": "cu_the_hoa|dan_chieu|cung_chu_de|khong",'
            ' "tin_cay": 0.0_den_1.0}]\n\n'
            "RANG BUOC:\n"
            "- don_vi_id phai la 1 id co trong DAU VAO 1 (vd 'TL-...:D1'), KHONG duoc la ten van ban me.\n"
            "- dieu_me_ids chi gom cac dieu_id da liet ke o DAU VAO 2.\n"
            "- Moi phan tu DAU VAO 1 phai co 1 ban ghi tra loi tuong ung.\n"
            "- Neu khong tim thay Dieu me phu hop: loai='khong', dieu_me_ids=[]."
        )},
    ]


TIER2_HE_THONG = HE_THONG_CHUNG + (
    " Nhiem vu: so sanh mot Dieu du thao voi cac Dieu me da duoc anh xa, "
    "phat hien cac loai loi noi dung. "
    "Chi ket luan khi trich duoc nguyen van can cu tu Dieu me; "
    "khong co can cu nguyen van thi ghi phu_hop."
)

LOAI_LOI_TIER2 = [
    "thu_hep_pham_vi", "mo_rong_pham_vi", "them_dieu_kien", "them_nghia_vu",
    "doi_so_lieu", "dat_thu_tuc_moi", "mau_thuan_truc_tiep", "vuot_tham_quyen",
    "trich_sai_nguyen_van", "phu_hop",
]


# 3 trang thai duy nhat cho tier2 Khoan.
TRANG_THAI_TIER2 = ["vi_pham", "hop_le", "chua_xac_dinh"]


TIER2_KHOAN_HE_THONG = HE_THONG_CHUNG + (
    " Nhiem vu: tham dinh MOT doan noi dung du thao bang cach so sanh voi cac Khoan me ung vien"
    " (lay tu semantic search). Phan loai vao DUNG 1 trong 3 trang thai:"
    "\n  - vi_pham: du thao TRAI/SAI so voi quy pham phap luat tuong ung."
    "\n  - hop_le: du thao PHU HOP voi quy pham phap luat (dung, hoac chat che hon nhung van"
    " trong khuon kho luat cho phep)."
    "\n  - chua_xac_dinh: KHONG co Khoan me nao thuc su dieu chinh CUNG VAN DE voi doan du thao."
    " Tuc la noi dung nay CO trong du thao nhung CHUA CO can cu phap ly de doi chieu."
    "\n\nQUY TRINH BAT BUOC (lam tuan tu):"
    "\nBUOC 1 - TIM CAN CU: Trong cac Khoan me ung vien, co Khoan nao THUC SU dieu chinh dung"
    " van de ma doan du thao dang noi khong? (ung vien chi gan ve ngu nghia, khong phai luc nao"
    " cung la can cu dung)."
    " Moi ung vien co truong 'phan'/'chuong' (vi tri trong cay van ban): dung CHU DE cua Phan/Chuong"
    " de xac dinh ung vien co dung mang van de khong; neu chu de Chuong lech han thi thuong khong phai can cu dung."
    "\n   - Neu KHONG co Khoan nao dung van de -> trang_thai = 'chua_xac_dinh'. Dung lai."
    "\n   - Neu CO -> chon Khoan me lien quan nhat lam can cu, sang BUOC 2."
    "\n   - NOI CAC KHOAN CUNG MOT DIEU/so_hieu: mot hinh thuc/hanh vi neu o khoan nay co the bi"
    " rang buoc boi THOI HAN/GIOI HAN o khoan khac cung Dieu. Vd 'dang tai cong TTDT' (khoan 2 la"
    " mot hinh thuc 'cong khai') bi rang buoc boi thoi han cong khai o khoan 1 cung Dieu -> dung"
    " thoi han do lam can cu, dung ket luan 'chua_xac_dinh' chi vi khong co khoan rieng."
    "\nBUOC 2 - SO SANH voi Khoan me lien quan nhat:"
    "\n   - Neu du thao PHU HOP -> trang_thai = 'hop_le'."
    "\n   - Neu du thao TRAI/SAI -> trang_thai = 'vi_pham'."
    "\n\n*** SO SANH SO LIEU THEO LOAI RANG BUOC (QUAN TRONG NHAT) ***"
    "\nMoi Khoan me ung vien co truong 'loai_rang_buoc' da duoc he thong nhan dien san"
    " (san/tran/co_dinh/trao_quyen/khong_ro). Khi du thao va Khoan me cung noi ve 1 con so"
    " (gio, ngay, thang, nam, %, tien, tuoi...), ap dung DUNG quy tac theo loai:"
    "\n  - 'san' (luat dat muc TOI THIEU: 'it nhat', 'toi thieu', 'khong thap hon'):"
    "\n       du thao THAP HON san -> vi_pham. Du thao BANG hoac CAO HON san -> hop_le."
    "\n       Vd luat 'it nhat 300%', du thao 250% -> vi_pham; du thao 350% -> hop_le."
    "\n  - 'tran' (luat dat muc TOI DA: 'khong qua', 'toi da', 'khong vuot qua'):"
    "\n       du thao CAO HON tran -> vi_pham. Du thao BANG hoac THAP HON tran -> hop_le."
    "\n       Vd luat 'khong qua 60 ngay', du thao 90 -> vi_pham; du thao 45 ngay -> hop_le."
    "\n       Vd luat 'khong qua 48 gio/tuan', du thao 44h -> hop_le (trong tran)."
    "\n  - 'co_dinh' (luat dat con so CO DINH: 'la', 'bang', khong co tu san/tran):"
    "\n       du thao KHAC con so do (cao hon HAY thap hon) -> vi_pham (doi so lieu)."
    "\n       Vd luat 'vao lop mot la 06 tuoi', du thao 07 tuoi -> vi_pham."
    "\n  - 'trao_quyen' (luat trao quyen tu quyet: 'do ... quy dinh', 'theo thoa thuan',"
    " 'hai ben thoa thuan'): du thao chon mot muc cu the trong pham vi duoc trao -> hop_le."
    "\n  - 'khong_ro': dua vao ngu canh de suy luan san/tran/co_dinh roi ap quy tac tren."
    "\nNEU du thao dat mot con so ma Khoan me KHONG he quy dinh con so do (luat chi trao quyen"
    " hoac khong de cap) va cung khong co Khoan me nao khac quy dinh -> chua_xac_dinh."
    "\n\nTIEU CHI 'vi_pham' khac (ngoai so lieu):"
    "\n  - LOAI TRU doi tuong ma luat bao ve: du thao 'chi/duy nhat/tru X' lam mat quyen doi tuong luat."
    "\n  - THEM doi tuong/dieu kien ma luat da loai tru, hoac trai gioi han luat."
    "\n  - TRICH DAN SAI: du thao dat trong dau nhay '...' noi dung luat nhung trich sai so/chu."
    "\n  - VUOT THAM QUYEN: VB cap duoi 'bai bo'/'sua doi' Khoan/Dieu cua Luat cap tren."
    "\n  - MAU THUAN truc tiep (vd luat 'co quyen'/tuy chon con du thao 'bat buoc')."
    "\n  - BO SOT DIEU KIEN lam SAI BAN CHAT: neu du thao chi dien dat gon hon nhung KHONG sai"
    " ban chat -> van hop_le; chi vi_pham khi viec bo sot lam TRAI quy pham (vd du thao dat"
    " dieu kien NGUOC voi luat)."
    "\n\nTIEU CHI 'hop_le' (du thao dung):"
    "\n  - Noi dung giong hoac dong nghia voi Khoan me."
    "\n  - So lieu thoa man rang buoc san/tran/co_dinh/trao_quyen nhu tren."
    "\n  - Du thao chi NHAC mot phan doi tuong/noi dung ma khong dung tu loai tru"
    " ('chi','duy nhat','rieng','tru') -> hop_le (khong loai tru ai)."
    "\n\nLUU Y - NOI DUNG HANH CHINH cua VB cap duoi LUON 'hop_le' (khong vi pham, khong phai"
    " chua_xac_dinh), du Khoan me khac: Dieu ve PHAM VI/DOI TUONG AP DUNG, GIOI HAN DIA BAN"
    " ('tren dia ban tinh H'), DIEU KHOAN THI HANH ('... chiu trach nhiem thi hanh'),"
    " HIEU LUC THI HANH ('co hieu luc tu ngay...'). Day la noi dung ky thuat soan thao,"
    " trong tham quyen co quan ban hanh."
    "\n\nCAN CU DA BI SUA: neu Khoan me mo dau bang khoi '[CAN CU NAY ... DUNG NOI DUNG SAU KHI SUA"
    " LAM CHUAN]' kem dong 'Noi dung sau khi sua: ...' -> LAY NOI DUNG SAU KHI SUA do lam chuan"
    " so sanh (uu tien hon ban goc phia duoi). Neu khoi ghi 'DA HET HIEU LUC' (bai bo) -> can cu"
    " khong con hieu luc; du thao van vien dan/mau thuan voi ban moi -> vi_pham, va neu con can cu"
    " khac phu hop thi dung can cu do."
    "\n\n'trich_dan' trong can_cu PHAI la nguyen van Khoan me lien quan (khong tom tat)."
)


def prompt_tier2_khoan(
    doan_du_thao: dict, khoan_ung_vien: list[dict],
    cap_du_thao: int | None, cap_me_cao_nhat: int | None,
) -> list[dict[str, str]]:
    """Prompt tier2: phan 1 doan du thao vao 3 trang thai vi_pham|hop_le|chua_xac_dinh."""
    vi_du = (
        "\nVI DU:"
        "\n[vi_pham - san] Khoan me 'it nhat 300%' (san); du thao 'it nhat 250%'"
        " -> vi_pham (duoi san)."
        "\n[vi_pham - tran] Khoan me 'khong qua 60 ngay' (tran); du thao 'khong qua 90 ngay'"
        " -> vi_pham (vuot tran)."
        "\n[vi_pham - co_dinh] Khoan me 'vao lop mot la 06 tuoi' (co_dinh); du thao '07 tuoi'"
        " -> vi_pham (doi so lieu co dinh)."
        "\n[vi_pham] Du thao 'bai bo khoan 2 Dieu 107 Bo luat Lao dong' -> vi_pham (vuot tham quyen)."
        "\n[hop_le - tran] Khoan me 'khong qua 48 gio/tuan' (tran); du thao 'khong qua 44 gio/tuan'"
        " -> hop_le (44 <= 48, trong tran). KHONG phai vi pham."
        "\n[hop_le - san] Khoan me 'it nhat 85% luong' (san); du thao 'it nhat 90%'"
        " -> hop_le (90 >= 85, tren san)."
        "\n[hop_le - trao_quyen] Khoan me 'thoi gian thu viec do hai ben thoa thuan' (trao_quyen);"
        " du thao dat 'khong qua 60 ngay' -> hop_le (trong pham vi trao quyen, khop luat)."
        "\n[hop_le] Khoan me 'NLD lam du 12 thang thi duoc nghi hang nam 12 ngay'; du thao 'NLD lam"
        " viec trong dieu kien binh thuong duoc nghi hang nam 12 ngay' -> hop_le. Du thao dien dat"
        " gon, con so 12 ngay KHOP luat, khong he mau thuan; viec khong nhac lai 'du 12 thang'"
        " KHONG lam sai ban chat -> KHONG vi pham."
        "\n[hop_le] Du thao 'to chuc, ca nhan gay o nhiem phai chi tra chi phi xu ly'; Khoan me"
        " 'co quan, to chuc, cong dong dan cu... gay o nhiem phai chi tra, boi thuong'"
        " -> hop_le (noi mot phan doi tuong, khong loai tru ai)."
        "\n[hop_le] Du thao 'Quyet dinh nay co hieu luc tu 01/7/2026' -> hop_le (noi dung hanh chinh)."
        "\n[hop_le] Du thao 'Giam doc So... chiu trach nhiem thi hanh Quyet dinh' -> hop_le (thi hanh)."
        "\n[chua_xac_dinh] Du thao 'phai nop phi bao ve moi truong 03 nam lien tuc truoc khi nop ho so';"
        " cac Khoan me ung vien chi noi ve ho so chung chung, khong Khoan nao quy dinh ve dieu kien"
        " nay -> chua_xac_dinh (noi dung moi, chua co can cu phap ly)."
    )
    return [
        {"role": "system", "content": TIER2_KHOAN_HE_THONG + vi_du},
        {"role": "user", "content": (
            "Doan du thao can tham dinh:\n" + str(doan_du_thao) + "\n\n"
            "Cac Khoan me ung vien (semantic search, co ngu canh truoc/sau neu co):\n"
            + str(khoan_ung_vien) + "\n\n"
            "Lam theo quy trinh 2 buoc. Tra DUNG 1 object JSON (khong markdown):"
            '\n{"trang_thai": "vi_pham|hop_le|chua_xac_dinh",'
            ' "can_cu": {"khoan_id": "<id Khoan me lien quan, rong neu chua_xac_dinh>",'
            ' "trich_dan": "<nguyen van Khoan me, rong neu chua_xac_dinh>"},'
            ' "noi_dung_du_thao": "<CHI khi vi_pham: CHEP CHINH XAC tung chu doan SAI'
            ' nam trong doan du thao - CHI phan sai thoi, KHONG chep lai ca doan vi dai va thua>",'
            ' "giai_thich": "<ly do ngan gon, neu ro diem khac biet neu vi_pham>",'
            ' "de_xuat_sua": "<CHI khi vi_pham: CHINH noi_dung_du_thao cho DUNG luat roi chep nguyen'
            ' ban DA SUA vao day. Day la CHUOI THAY THE truc tiep cho noi_dung_du_thao (thay snippet'
            ' sai bang chuoi nay la van ban dung luat). TUYET DOI KHONG viet dang huong dan/menh lenh'
            ' nhu \'Sua X thanh Y\', \'nen sua...\', \'can thay...\'; chi ghi dung van ban sau khi sua.'
            ' Vd noi_dung_du_thao=\'tu 13 den 17 nguoi\' -> de_xuat_sua=\'tu 23 den 27 nguoi\'>",'
            ' "tin_cay": 0.0}'
        )},
    ]


def prompt_tier2(
    dieu_du_thao: dict, dieu_me_list: list[dict], cap_du_thao: int | None, cap_me_cao_nhat: int | None,
) -> list[dict[str, str]]:
    thong_tin_cap = ""
    if cap_du_thao is not None and cap_me_cao_nhat is not None:
        thong_tin_cap = f"\nCap du thao = {cap_du_thao}, cap me cao nhat = {cap_me_cao_nhat}.\n"
    return [
        {"role": "system", "content": TIER2_HE_THONG},
        {"role": "user", "content": (
            "Dieu du thao (du Khoan):\n" + str(dieu_du_thao) + "\n\n"
            "Cac Dieu me duoc anh xa (nguyen van, co ghi 'da sua boi' neu co):\n" + str(dieu_me_list) + "\n"
            + thong_tin_cap +
            "\nTra JSON mang [{so_khoan_du_thao, loai_loi, muc_do, tin_cay, "
            "can_cu:{dieu_me_id, so_khoan, trich_dan}, giai_thich, de_xuat_sua}]. "
            f"loai_loi thuoc: {LOAI_LOI_TIER2}. muc_do thuoc cao|trung_binh|thap. "
            "tin_cay 0..1. phu_hop khong ghi vao DB nhung co the de nghi so sanh."
        )},
    ]

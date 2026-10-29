# Ví dụ đầu vào → đầu ra (văn bản minh họa, không phải nguyên văn thật)

## Cấu trúc

Đầu vào (sau normalize):
```
Chương II
HỢP ĐỒNG LAO ĐỘNG
Mục 1. GIAO KẾT HỢP ĐỒNG LAO ĐỘNG
Điều 13. Hợp đồng lao động
1. Hợp đồng lao động là sự thỏa thuận ...
2. Trước khi nhận người lao động vào làm việc ...
Điều 14. Hình thức hợp đồng lao động
1. Hợp đồng lao động phải được giao kết bằng văn bản ...
a) Hợp đồng được giao kết thông qua phương tiện điện tử ...
b) Hai bên có thể giao kết hợp đồng lao động bằng lời nói ...
Điều 14a.
1. ...
```
Đầu ra:
```
Dieu(so_dieu='13', so_dieu_num=13, chuong_so='II', chuong_ten='HỢP ĐỒNG LAO ĐỘNG', muc_so='1', tieu_de='Hợp đồng lao động', thu_tu=13)
Khoan(dieu='13', so_khoan='1', diem=None, ...), Khoan(dieu='13', so_khoan='2', ...)
Dieu(so_dieu='14', tieu_de='Hình thức hợp đồng lao động')
Khoan(dieu='14', so_khoan='1'), Khoan(dieu='14', so_khoan='1', diem='a', parent='...:K1'), Khoan(..., diem='b')
Dieu(so_dieu='14a', so_dieu_num=14, tieu_de='')     # tiêu đề rỗng hợp lệ
```

Test âm: dòng `1. Thời hạn ...` nằm trong ngoặc kép của một lệnh sửa đổi → không tạo Khoản.

## Căn cứ

```
Căn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015;
Căn cứ Bộ luật Lao động ngày 20 tháng 11 năm 2019;
Theo đề nghị của Bộ trưởng ...
```
→ `[CanCuTho(ten='Luật Tổ chức Chính phủ', nam=2015), CanCuTho(ten='Bộ luật Lao động', nam=2019)]`

## Lệnh sửa đổi

| Đầu vào | Đầu ra |
|---|---|
| `Sửa đổi khoản 2 Điều 54 như sau: "2. ..."` | `LenhSuaDoi(loai=sua_doi, so_dieu='54', so_khoan='2', noi_dung_moi='2. ...')` |
| `Sửa đổi, bổ sung điểm b khoản 3 Điều 12 như sau:` | `(sua_doi, so_dieu='12', so_khoan='3', diem='b')` |
| `Bổ sung Điều 54a vào sau Điều 54 như sau:` | `(bo_sung, so_dieu='54a', vi_tri='sau', moc_so_dieu='54')` |
| `Bổ sung khoản 5 vào sau khoản 4 Điều 20 như sau:` | `(bo_sung, so_dieu='20', so_khoan='5', vi_tri='sau', moc_so_khoan='4')` |
| `Bãi bỏ khoản 4 Điều 58 và Điều 60.` | hai lệnh `(bai_bo, '58','4')`, `(bai_bo, '60', None)` |
| `Thay cụm từ "Sở Kế hoạch" bằng cụm từ "Sở Tài chính" tại Điều 10, Điều 12` | `(thay_cum_tu, cum_tu_cu, cum_tu_moi, dieu_list=['10','12'])` |
| `Sửa tên Chương III thành ...` | không khớp → `(sua_doi, noi_dung_moi=nguyên văn, tin_cay=can_ra_soat)` + WARNING |

## Dẫn chiếu

| Đầu vào | Đầu ra |
|---|---|
| `theo quy định tại khoản 2 Điều 54 của Luật này` | `DanChieu(so_khoan='2', so_dieu='54', vb='Luật này')` |
| `quy định tại Điều 10 Bộ luật Dân sự` | `DanChieu(so_dieu='10', ten_van_ban='Bộ luật Dân sự')` |
| `các Điều 10, 12 và 15 Nghị định 01/2021/NĐ-CP` | 3 `DanChieu`, `so_hieu='01/2021/NĐ-CP'` |
| `điểm b khoản 1 Điều 14 Bộ luật Lao động 2019` | `(diem='b', so_khoan='1', so_dieu='14', ten='Bộ luật Lao động', nam=2019)` |
| `tại Chương II Luật này` | `DanChieu(so_dieu=None, text_dan='Chương II Luật này')` |

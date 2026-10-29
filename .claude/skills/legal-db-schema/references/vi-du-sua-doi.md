# Ví dụ: một văn bản sửa đổi đi vào DB như thế nào

Văn bản giả định để minh họa cấu trúc (không phải văn bản thật).

```
NGHỊ ĐỊNH 12/2026/NĐ-CP  Sửa đổi, bổ sung một số điều của Nghị định 01/2021/NĐ-CP
Điều 1. Sửa đổi, bổ sung một số điều của Nghị định 01/2021/NĐ-CP
1. Sửa đổi khoản 2 Điều 54 như sau:
"2. Thời hạn cấp Giấy chứng nhận đăng ký doanh nghiệp là 02 ngày làm việc ..."
2. Bổ sung Điều 54a vào sau Điều 54 như sau:
"Điều 54a. Đăng ký doanh nghiệp qua mạng ..."
3. Bãi bỏ khoản 4 Điều 58.
Điều 2. Hiệu lực thi hành
Nghị định này có hiệu lực từ ngày 01 tháng 3 năm 2026.
```

## Bước 1 – ingest ghi lệnh (`amend_parser.py` → `repo_van_ban.ghi_lenh`)

| nguon_id | dich_id | loai | dich_so_dieu | dich_so_khoan | vi_tri | ngay_hieu_luc | noi_dung_moi | nguon_lenh | da_ap_dung |
|---|---|---|---|---|---|---|---|---|---|
| ND-2026-12 | ND-2021-01 | sua_doi | 54 | 2 | | 2026-03-01 | "2. Thời hạn cấp ... 02 ngày ..." | D1:K1 | false |
| ND-2026-12 | ND-2021-01 | bo_sung | 54a | | sau 54 | 2026-03-01 | "Điều 54a. ..." | D1:K2 | false |
| ND-2026-12 | ND-2021-01 | bai_bo | 58 | 4 | | 2026-03-01 | | D1:K3 | false |

`dich_dieu_id`/`dich_khoan_id` còn NULL: chưa phân giải.

## Bước 2 – `sync.py` thi hành

| Bản ghi | Thay đổi |
|---|---|
| `khoan ND-2021-01:D54:K2` (cũ) | `hieu_luc_den='2026-02-28'`, `trang_thai='het_hieu_luc'`, `thay_boi_id='ND-2021-01:D54:K2@2026-03-01'` |
| `khoan ND-2021-01:D54:K2@2026-03-01` (mới) | `hieu_luc_tu='2026-03-01'`, `nguon_sua_doi_id='ND-2026-12'`, nội dung mới |
| `dieu_luat ND-2021-01:D54a` (mới) | `so_dieu='54a'`, `so_dieu_num=54`, `thu_tu` sau Điều 54, parse Khoản con |
| `khoan ND-2021-01:D58:K4` | `trang_thai='bai_bo'`, `hieu_luc_den='2026-02-28'` |
| 3 dòng `quan_he_van_ban` | `dich_dieu_id`, `dich_khoan_id` điền; `da_ap_dung=true` |
| `van_ban ND-2021-01` | `trang_thai` tính từ view → `het_hieu_luc_mot_phan` |

## Bước 3 – tra cứu

```sql
SELECT * FROM khoan_hieu_luc_tai('ND-2021-01','54','2',NULL,'2026-02-01');  -- bản cũ
SELECT * FROM khoan_hieu_luc_tai('ND-2021-01','54','2',NULL,'2026-06-01');  -- bản mới
SELECT * FROM khoan_hieu_luc_tai('ND-2021-01','58','4',NULL,'2026-06-01');  -- NULL → bãi bỏ
SELECT so_dieu, da_sua FROM ban_hop_nhat('ND-2021-01','2026-06-01') ORDER BY thu_tu;  -- có 54a, 54 da_sua=true
```

---
name: legal-db-schema
description: Quy ước cơ sở dữ liệu của audit_rag (PostgreSQL + pgvector) cho kho pháp luật Việt Nam - id, phiên bản theo thời gian, trạng thái hiệu lực, đồ thị quan_he_van_ban, các hàm SQL (khoan_hieu_luc_tai, ban_hop_nhat, van_ban_me_qua_do_thi), quy tắc viết migration và repo. Dùng skill này mỗi khi chạm vào migrations/, app/db/, bất kỳ câu SQL nào, khi quyết định lưu dữ liệu vào bảng nào, hoặc khi người dùng nói "thêm cột", "sửa bảng", "tra hiệu lực", "văn bản sửa đổi", "bản hợp nhất", "văn bản mẹ".
---

# Cơ sở dữ liệu kho pháp luật

Kho lưu **lịch sử và quan hệ**, không chỉ trạng thái hiện tại, để tính được "quy định nào có hiệu lực tại ngày X" cho bất kỳ ngày nào, giải thích được và sửa được khi parser sai. Schema đầy đủ ở `PLAN.md` mục 4 và `migrations/001_init.sql`; skill này nói cách dùng nó đúng.

## Ba nhóm bảng

| Nhóm | Bảng | Quy tắc |
|---|---|---|
| Nguồn sự thật | `van_ban`, `dieu_luat`, `khoan`, `quan_he_van_ban`, `dan_chieu` | Chỉ thêm. Sửa nội dung = phiên bản mới. Không DELETE khi thử nghiệm |
| Dẫn xuất | `chunk` | Xóa/tạo lại tùy ý (`ingestion/chunks.py`, GĐ E) |
| Ứng dụng | `tai_lieu`, `tai_lieu_don_vi`, `phien_doi_chieu`, `phien_van_ban_me`, `anh_xa_dieu`, `ket_qua_doi_chieu`, `tier2_cache`, `eval_*` | Theo phiên; `ket_qua_doi_chieu` luôn trỏ về bản ghi thật của nguồn sự thật |

Nếu một thông tin cần cho tra cứu chỉ nằm ở bảng dẫn xuất hoặc trong `jsonb`, đưa nó thành cột ở nguồn sự thật.

## ID

```
van_ban.id    'BLLD-2019-45'  (người dùng đặt; hoặc sinh từ số hiệu 45/2019/QH14 → QH14-2019-45)
dieu_luat.id  f"{van_ban_id}:D{so_dieu}"      so_dieu TEXT ('13', '54a'); so_dieu_num để sắp xếp
khoan.id      f"{dieu_id}:K{so_khoan}"        Điểm: f"{khoan_id}:D{diem}"
phiên bản     id gốc + '@YYYY-MM-DD'          ngày hiệu lực của lệnh sửa; bản gốc giữ id
tai_lieu_don_vi.id  'TL-x:D5' | 'TL-x:D5:K2' | 'TL-x:P12' (đoạn) | 'TL-x:C3' (cụm)
```

Hiển thị cho người dùng: bỏ hậu tố `@`, ghi "Điều 54 (sửa đổi bởi NĐ 12/2026, hiệu lực 01/03/2026)".

## Hiệu lực theo thời gian

Mỗi `dieu_luat`/`khoan` có `hieu_luc_tu`, `hieu_luc_den`, `trang_thai`, `thay_boi_id`, `nguon_sua_doi_id`.

- **Luôn tra theo ngày** bằng hàm: `khoan_hieu_luc_tai(van_ban_id, so_dieu, so_khoan, diem, ngay)`, `dieu_hieu_luc_tai(...)`, `ban_hop_nhat(van_ban_id, ngay)`. Không viết lại điều kiện ngày trong Python; không bỏ lọc ngày.
- Ngày tra của một phiên đối chiếu = `tai_lieu.ngay_du_kien`, mặc định `settings.HIEU_LUC_MAC_DINH`.
- `van_ban.trang_thai` chỉ do `ingestion/sync.py` ghi từ view `van_ban_trang_thai_tinh`. Không UPDATE tay. Giá trị: `chua_hieu_luc | con_hieu_luc | het_hieu_luc_mot_phan | het_hieu_luc`.
- `tin_cay ∈ xac_nhan | can_ra_soat` ở mọi bảng nguồn; kết quả dựa trên bản ghi `can_ra_soat` phải mang cờ ra ngoài (`ket_qua_doi_chieu.can_cu_tin_cay`).

## Đồ thị `quan_he_van_ban`

Lưu **sự kiện**: `nguon_id --loai--> dich_id [dich_so_dieu, dich_so_khoan, dich_diem]`, `loai ∈ sua_doi | bo_sung | thay_the | bai_bo | huong_dan | quy_dinh_chi_tiet | can_cu | thay_cum_tu`.

- Parser (`amend_parser.py`, phần Căn cứ) **chỉ ghi lệnh** với `da_ap_dung=false`, giữ số Điều/Khoản dạng thô. Phân giải `dich_dieu_id`/`dich_khoan_id` và thi hành là việc của `sync.py`. Văn bản đích chưa nạp → `loi_ap_dung='chua_nap_van_ban_dich'`, lệnh chờ.
- Thi hành (`sync.py`), mỗi lệnh một transaction, idempotent qua `da_ap_dung`:
  - `sua_doi`: bản cũ `hieu_luc_den = ngay-1`, `trang_thai='het_hieu_luc'`, `thay_boi_id` → bản mới `@ngay` với `hieu_luc_tu = ngay`, `nguon_sua_doi_id`.
  - `bo_sung`: tạo mới, `thu_tu` theo `vi_tri`, đánh lại `thu_tu` cả văn bản.
  - `bai_bo`: `trang_thai='bai_bo'`, `hieu_luc_den = ngay-1`, không bản mới.
  - `thay_cum_tu`: với mỗi Điều liệt kê, tạo phiên bản mới có cụm từ thay.
  - `thay_the`/`bai_bo` cả văn bản: mọi Điều/Khoản `het_hieu_luc`, `van_ban.ngay_het_hieu_luc`, `ly_do_het`.
  - Cuối: cập nhật `van_ban.trang_thai` từ view; nếu `ENABLE_FALLBACK` thì rebuild `chunk` cho Điều bị chạm.
- Đi lên cây thẩm quyền: `van_ban_me_qua_do_thi(ids)` theo `quy_dinh_chi_tiet | huong_dan | can_cu`, tối đa 2 bước. Không đi xuống (không kéo thông tư con).

Ví dụ một văn bản sửa đổi đi qua các bảng: `references/vi-du-sua-doi.md`.

## Migration

- v3 bắt đầu từ `001_init.sql`. Thay đổi sau đó = file số kế tiếp, **không sửa file đã áp dụng**, không đổi tên bảng/cột.
- Tương thích ngược: `ADD COLUMN IF NOT EXISTS` có default/nullable; hàm `CREATE OR REPLACE` với tham số mới có `DEFAULT`.
- `BEGIN; ... COMMIT;`; `scripts/init_db.py` ghi `schema_migrations`, chạy hai lần không lỗi.
- HNSW index cho `chunk.embedding` tạo sau khi nạp (GĐ E), không trong migration.

## Repo layer (`app/db/`)

- `session.py`: một `ConnectionPool` từ `settings.DB_URL`; hàm `get_conn()` context manager. Module khác không tạo connection riêng.
- `repo_van_ban.py` (nguồn sự thật), `repo_hieu_luc.py` (hàm tra + thi hành lệnh), `repo_tai_lieu.py`, `repo_audit.py`. Mỗi hàm repo: nhận kiểu pydantic/scalar, trả pydantic, SQL tham số hóa, không ghép chuỗi.
- Upsert `INSERT ... ON CONFLICT (id) DO UPDATE SET ...`; nạp lại cùng văn bản phải idempotent.
- Ghi nhiều dòng dùng `executemany` hoặc `COPY`; không vòng lặp commit từng dòng.
- Embedding truyền dạng `list[float]` với cast `::vector`.
- Repo không bắt exception để nuốt; để `psycopg.Error` nổi lên, tầng gọi quyết định.

## Kiểm tra trước khi commit

- [ ] Mọi tra cứu Điều/Khoản đi qua hàm SQL theo ngày.
- [ ] Không UPDATE `trang_thai`/`hieu_luc_*` ngoài `sync.py`.
- [ ] Parser không chạm `dieu_luat`/`khoan`; chỉ ghi `quan_he_van_ban`.
- [ ] SQL chỉ trong `app/db/`; migration mới có số kế tiếp, chạy 2 lần OK.
- [ ] `ket_qua_doi_chieu` ghi `can_cu_*` là id thật (FK sẽ chặn, nhưng kiểm tra trước khi insert để báo lỗi rõ).

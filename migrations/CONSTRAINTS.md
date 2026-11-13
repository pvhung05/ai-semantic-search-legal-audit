# Ràng buộc — cơ sở dữ liệu

1. **Không sửa file migration đã áp dụng.** Thay đổi mới = file số kế tiếp (`018_<mo_ta>.sql`). `scripts/init_db.py` nhận diện migration theo tên file trong `schema_migrations`, nên sửa file cũ sẽ không bao giờ chạy lại trên DB đã có.
2. Migration phải **chạy lại an toàn**: `CREATE ... IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` (nullable hoặc có default), `CREATE OR REPLACE FUNCTION` với tham số mới có `DEFAULT`. Mỗi file chạy trong một transaction.
3. Đặt bảng vào đúng schema (`danhmuc` / `vanban` / `rag`, xem [ARCHITECTURE.md](ARCHITECTURE.md)); ghi rõ tên schema trong DDL.
4. **Cột embedding là `vector(1024)`** — gắn với bge-m3 (`EMBED_DIM`). Đổi model embedding = migration đổi cột + embed lại toàn bộ `rag.chunk` và `rag.du_thao_node`.
5. Code Python vào DB **chỉ qua `app.core.db.session.ket_noi()`**, SQL tham số hóa (`%s`), không ghép chuỗi. Không ORM.
6. `vanban.node` / `rag.chunk` là **dữ liệu dẫn xuất** (dựng lại bằng `build-cay`); bảng crawl ở `vanban` là nguồn sự thật. Sửa dữ liệu sai → sửa ở nguồn hoặc ở loader rồi build lại, không UPDATE tay `node`/`chunk`.
7. Thứ tự dựng kho: `build-cay` cho cả văn bản nguồn lẫn đích **trước** `port-impacts`, nếu không `tac_dong.node_nguon_id` bị NULL.
8. Không có DB test riêng: test cần DB thật đánh dấu `@pytest.mark.integration` và không chạy trong `check`.

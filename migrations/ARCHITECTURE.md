# migrations — schema PostgreSQL 16 + pgvector

Một database, 3 schema (từ migration 013). `search_path = vanban, danhmuc, rag, public` được đặt ở cấp database nên code gọi tên bảng trần (`node`, `chunk`). Ràng buộc khi sửa: [CONSTRAINTS.md](CONSTRAINTS.md).

| Schema | Ai ghi | Bảng chính |
|---|---|---|
| `danhmuc` | crawl | danh mục vbpl: `loai_vanban`, `coquan_banhanh`, `linhvuc`, `relation_types`… |
| `vanban` (crawl) | `app/crawl` | `documents`, `document_content` (HTML), `document_relations`, `document_cay` (cây JSON thô, cờ `da_build`), `crawl_queue` (cờ `da_fetch_tac_dong`), `provision_impacts`, `action_config` |
| `vanban` (kho cây) | `app/doisanh` | `van_ban`, `node` (adjacency list mọi cấp), `tac_dong` (cạnh sửa đổi cấp điều khoản), view `v_tac_dong` |
| `rag` | `app/doisanh` | `chunk` (`text_goc`, `text_embed`, `embedding vector(1024)`, `tsv_goc`, `hieu_luc_tu/den`), `du_thao`, `du_thao_node` |
| `public` | `scripts/init_db.py` | `schema_migrations`, extension pgvector |

**Quyết định thiết kế**
- **Model hiện hành bắt đầu từ 003** (cây `node` + `chunk`). `001_init.sql` là schema v3 cũ (`dieu_luat`/`khoan`, các hàm `khoan_hieu_luc_tai`, `ban_hop_nhat`…); phần lớn đã bị 003/012 drop — đừng dựa vào nó để hiểu DB hiện tại.
- `node.id` là **UUID của vbpl**, không tự ghép. `duong_dan` mã hóa vị trí: `CI>D5>K1>da` = Chương I › Điều 5 › Khoản 1 › điểm a.
- **Truy hồi viết trong SQL**: `tim_kiem_hybrid()` (007) = vector cosine + BM25 (`tsvector` cấu hình `simple`, không tách từ tiếng Việt) hợp nhất RRF, lọc hiệu lực theo ngày và theo `p_van_ban_ids`. Tham số `p_cap_max`, `p_linh_vuc` còn trong chữ ký nhưng **không có tác dụng**.
- Chỉ mục HNSW cho vector cosine trên `rag.chunk.embedding` được bổ sung ở migration 018 (`chunk_embedding_hnsw`).

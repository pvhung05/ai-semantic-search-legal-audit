---
name: legal-db-schema
description: Quy ước cơ sở dữ liệu của audit-legal (PostgreSQL 16 + pgvector, 3 schema danhmuc/vanban/rag) - cây node + chunk, tác động sửa đổi, hàm tim_kiem_hybrid, hiệu lực theo ngày, quy tắc viết migration và SQL. Dùng skill này mỗi khi chạm vào migrations/, app/doisanh/db/, app/crawl/store.py, app/doisanh/public_loader.py, bất kỳ câu SQL nào, khi quyết định lưu dữ liệu vào bảng nào, hoặc khi người dùng nói "thêm cột", "sửa bảng", "migration", "tra hiệu lực", "văn bản sửa đổi", "tác động", "chunk", "embedding".
---

# Cơ sở dữ liệu kho pháp luật

Nguồn chính, đọc trước:
- [migrations/ARCHITECTURE.md](../../../migrations/ARCHITECTURE.md) — 3 schema, bảng nào ai ghi, `node`/`chunk`/`tac_dong`, `tim_kiem_hybrid()`.
- [migrations/CONSTRAINTS.md](../../../migrations/CONSTRAINTS.md) — quy tắc bắt buộc khi viết migration và SQL.

Skill này chỉ bổ sung cách làm việc thường gặp.

## Thêm hoặc đổi cấu trúc

1. Tạo `migrations/0NN_<mo_ta>.sql` với số kế tiếp; DDL ghi rõ schema (`vanban.`, `rag.`, `danhmuc.`); dùng `IF NOT EXISTS` / `CREATE OR REPLACE`.
2. `python scripts/init_db.py` hai lần — lần 2 phải báo "bo qua".
3. Sửa code ghi/đọc: crawl → `app/crawl/store.py`; kho cây → `app/doisanh/public_loader.py`; dự thảo → `app/doisanh/db/repo_tai_lieu.py`; truy hồi → `app/doisanh/retrieval/`.
4. Cập nhật `migrations/ARCHITECTURE.md` nếu bảng/cột có ý nghĩa mới, trong cùng commit.

## Hiệu lực và sửa đổi (model hiện hành)

- Hiệu lực nằm trên `rag.chunk.hieu_luc_tu/hieu_luc_den`; lọc theo ngày bên trong `tim_kiem_hybrid(p_ngay)`. Không lọc lại trong Python.
- Sửa đổi cấp điều khoản là cạnh `vanban.tac_dong (node_dich_id ← node_nguon_id)`, port từ `vanban.provision_impacts` bằng `python -m app.doisanh.cli port-impacts` (sau `build-cay`). `retrieval/can_cu.py` gắn nội dung sau sửa vào đầu căn cứ.
- `node`/`chunk` là dẫn xuất: sửa sai → sửa loader/nguồn rồi `build-cay` lại, không UPDATE tay.

## SQL trong Python

- Kết nối qua `app.core.db.session.ket_noi()`; tự `conn.commit()` (pool `autocommit=False`).
- Tham số `%s`, không f-string ghép giá trị. Embedding truyền `list[float]` với cast `::vector`.
- Ghi nhiều dòng: `executemany`, không commit từng dòng.
- Không nuốt `psycopg.Error` trong repo; để tầng gọi quyết định.

## Di sản — đừng dùng làm mẫu

`migrations/001_init.sql`, `app/doisanh/db/repo_van_ban.py`, `repo_hieu_luc.py`, `repo_audit.py`, `app/doisanh/ingestion/sync.py` và `references/vi-du-sua-doi.md` mô tả schema v3 (`dieu_luat`, `khoan`, `quan_he_van_ban`, hàm `khoan_hieu_luc_tai`, `ban_hop_nhat`, phiên bản `id@YYYY-MM-DD`). Schema này đã bị migration 003/012 drop; chỉ đọc để hiểu lịch sử.

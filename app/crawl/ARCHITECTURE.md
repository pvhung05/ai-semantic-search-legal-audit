# app/crawl — service thu thập từ vbpl.vn

**Trách nhiệm:** lấy metadata, toàn văn HTML, quan hệ, cây nội dung và tác động sửa đổi cấp điều khoản của văn bản pháp luật từ vbpl.vn, ghi vào schema `vanban` (+ danh mục vào `danhmuc`). Ràng buộc bắt buộc: [CONSTRAINTS.md](CONSTRAINTS.md).

**Giao diện với module khác**
- Chỉ import `app/core`. **Không import `app/doisanh`** và ngược lại — hai service chỉ gặp nhau qua DB.
- Đầu ra mà `app/doisanh` đọc: `vanban.document_cay` (cây JSON thô), `vanban.provision_impacts` (tác động), `vanban.document_content` (HTML toàn văn), `vanban.documents`.
- Entry: `python -m app.crawl.cli <lệnh>` ([cli.py](cli.py)). Thứ tự chuẩn:
  `seed-actions` → `seed-catalogs` → `discover` → `crawl` (hoặc `crawl-full` = crawl + fetch-cay) → `fetch-cay` → `fetch-tac-dong`. `stats` để xem tiến độ.

**Quyết định thiết kế**
- vbpl.vn là app Next.js: dữ liệu lấy bằng **POST Server Action** + parse **RSC flight payload** ([parser.py](parser.py), [doc_api.py](doc_api.py)), không có API công khai. Action-id được sniff tay, lưu ở [actions.py](actions.py) và bảng `vanban.action_config`.
- `fetch-cay`/`fetch-tac-dong` **chạy tăng dần**: chỉ lấy văn bản chưa có cây / chưa có cờ `da_fetch_tac_dong` (migration 017). `--all` để lấy lại hết.
- Toàn bộ SQL ghi của service nằm trong [store.py](store.py).
- `scripts/fetch_*.py` là script thăm dò từng API vbpl khi cần debug/sniff lại, không thuộc luồng chính.

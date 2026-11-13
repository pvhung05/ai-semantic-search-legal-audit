# Ràng buộc — app/crawl

1. **Chỉ module này được gọi mạng ra vbpl.vn.** Code ở `app/doisanh` phải đọc dữ liệu crawl từ DB, không fetch trực tiếp.
2. **Tuần tự, một luồng, có giãn cách.** `Fetcher` ngủ ngẫu nhiên `CRAWL_DELAY_MIN..MAX` giây giữa 2 request và retry có backoff. Không song song hóa, không hạ delay khi chạy batch lớn — rủi ro bị vbpl chặn IP.
3. **Lỗi 400/404 khi POST Server Action = action-id đã đổi** (vbpl deploy lại). Cách xử lý: sniff lại action-id từ trình duyệt → cập nhật [actions.py](actions.py) → `python -m app.crawl.cli seed-actions`. Không đoán action-id.
4. Ghi DB qua [store.py](store.py), upsert idempotent: chạy lại một lệnh crawl trên cùng văn bản không được tạo bản ghi trùng.
5. Muốn thay đổi schema `vanban` → migration mới (xem [migrations/CONSTRAINTS.md](../../migrations/CONSTRAINTS.md)), rồi kiểm tra `app/doisanh/public_loader.py` vẫn đọc được.

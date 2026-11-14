# PROGRESS

Cập nhật cuối mỗi phiên làm việc (xem quy tắc trong [AGENTS.md](AGENTS.md)). Ghi ngày tuyệt đối.

## Đã xong

- Crawler vbpl.vn (Server Action + RSC), schema metadata, catalog, cây nội dung, tác động cấp điều khoản — `app/crawl`.
- Kho luật dạng cây `node` + `chunk` (node lá có ngữ cảnh cha), embedding bge-m3, tách 3 schema `danhmuc`/`vanban`/`rag` (migration 003–017).
- Tách 2 service `crawl` / `doisanh` dùng chung `core`.
- Truy hồi lai (vector + BM25 + RRF trong SQL) → rerank TEI → gộp anh em lên Khoản/Điều; gắn nội dung sau sửa đổi vào căn cứ.
- `/audit` stateless (3 nhóm VI_PHAM / HOP_LE / CHUA_XAC_DINH) + DOCX track-change; `/ask` có dẫn chiếu và nhớ lịch sử; UI xem toàn văn HTML vbpl.
- 13/11/2026: harness tài liệu cho agent (`AGENTS.md`, `ARCHITECTURE.md`/`CONSTRAINTS.md` theo module, `tasks.py`).

## Đang làm

- **Tinh chỉnh để Qwen3:14b (model chính) phát hiện lỗi và đề xuất sửa đoạn dự thảo tốt hơn** — `app/doisanh/audit/prompts.py`, `so_sanh.py`: đã tách cascade 2-pass (Pass 1 phân loại nhanh `think=False`, Pass 2 suy luận sâu `think=True` sinh đề xuất sửa cho các mục vi phạm).
  - Dự thảo mẫu để kiểm tay và 5 ca thử nằm ở đâu (`data/` bị `.gitignore`): TODO: cần xác nhận.

## Bị chặn

- Không có.

## Tiếp theo (thứ tự ưu tiên đã xác nhận)

1. **Kiểm trích dẫn nguyên văn** trong `so_sanh.py`: `rapidfuzz.partial_ratio(trich_dan, căn cứ đã đưa vào prompt) ≥ 85`, không đạt → hạ `CHUA_XAC_DINH`. Chi tiết: [app/doisanh/audit/CONSTRAINTS.md](app/doisanh/audit/CONSTRAINTS.md).
2. **Bộ đánh giá có nhãn** cho luồng hiện tại: dữ liệu (đoạn dự thảo → verdict + căn cứ đúng) từ dự thảo thật đã được người duyệt; viết lại công cụ eval cho `chay_tier2`; chạy mỗi khi đổi prompt / model / tham số retrieval.

Đã quyết định nhưng chưa xếp thứ tự:
- **Đổi tên toàn bộ code sang tiếng Anh** (hàm, biến, module; quyết định 13/11/2026, chưa bắt đầu). Làm thành đợt riêng, theo từng module, mỗi module một commit, `python tasks.py check` xanh sau mỗi bước; cập nhật tài liệu module trong cùng commit. Vị trí trong thứ tự ưu tiên: TODO: cần xác nhận.

Ý tưởng, chưa quyết: tách từ tiếng Việt cho BM25 (hiện `tsvector` cấu hình `simple`) nếu đo được recall thấp.

## Mốc thời gian

- Hạn nộp / bảo vệ KLTN: TODO: cần xác nhận.

## Nhật ký phiên

- 14/11/2026 — branch `feat/ai-agent`: tạo bộ prompt chuyên biệt cho Public LLM (Gemini, Claude, GPT):
  - Pass 1 (`prompt_tier2_khoan_public`): thiết kế tiếng Việt chuẩn 100%, cấu trúc Markdown rành mạch, đưa trường `giai_thich` lên trước `trang_thai` trong JSON schema để mô hình thực hiện Chain-of-Thought trước khi chốt kết luận, giải quyết dứt điểm tình trạng Gemini phán đoán vội vã.
  - Pass 2 (`prompt_tier2_de_xuat_public`): tối ưu định vị `noi_dung_sai` và sinh `de_xuat_sua` chuẩn văn phong lập pháp Việt Nam; hỗ trợ trả về chuỗi rỗng khi bãi bỏ trường hợp tự ý đặt thêm trái luật.
  - Tự động kích hoạt khi gọi với `is_local=False` (hoặc `.env` cấu hình `IS_LOCAL=false`) trong `so_sanh_chunk` và `de_xuat_sua_chunk`. Bổ sung 4 unit test trong `test_so_sanh_cascade.py`.
- 14/11/2026 — branch `feat/ai-agent`: hoàn thành toàn diện 13/13 hạng mục audit theo báo cáo ponytail:
  - Finding 1 (`56a05dc`): Sửa `segment.py` không bỏ qua đoạn văn xuôi khi dự thảo không có đề mục La Mã (mặc định tiêu đề "Nội dung").
  - Finding 2, 3, 5, 7 (`f880db2`): Thêm `la_id_hop_le()` chặn path traversal ở `file_store.py` và `routes_simple.py`; đặt ngưỡng upload 25MB (HTTP 413); trả về 501 cho `/upload/legal` do nạp thủ công chưa hỗ trợ trên schema cây; bỏ lời gọi sinh embedding thừa khi upload draft.
  - Finding 4 (`38baa51`): Bổ sung migration 018 tạo chỉ mục vector HNSW (`chunk_embedding_hnsw`) trên `rag.chunk` với `vector_cosine_ops`.
  - Finding 9 (`548742f`): Tái sử dụng `httpx.Client()` connection pool keep-alive cho cả LLM và Embedder thay vì mở mới từng request.
  - Finding 8, 10, 11 (`5ae0413`): Tôn trọng tham số `top_k` tại `/ask`; lọc trùng lặp cell trong bảng Word có merge cells; cache `vb_cache` và `dieu_cache` tránh truy vấn N+1 lặp lại trong `nap_khoan_ung_vien`.
  - Finding 13 (`8a16459`): Thống nhất thư viện HTTP, chuyển `fetcher.py` và `rerank.py` từ `requests` sang `httpx`, gỡ bỏ hoàn toàn `requests` khỏi `requirements.txt`.
  - Finding 12 (`8f64ae5`): Bổ sung test offline cho `file_store.py` và các API endpoints trong `routes_simple.py`, kiểm thử độc lập không phụ thuộc socket loopback trong môi trường sandbox.
  - Finding 6 (`4a10719`): Dọn dẹp dứt điểm ~1.900 dòng mã di sản: gỡ bỏ toàn bộ 9 module workflow stateful cũ bám schema đã drop và 6 scripts di sản không còn dùng; cập nhật tài liệu kiến trúc.
- 13/11/2026 — branch `feat/ai-agent`: sửa lỗi Word Track Changes loại bỏ cả đoạn thay vì chỉ xóa phần sai: (1) sửa `docx_track.py` áp dụng Track Changes ngay cả khi `de_xuat_sua` rỗng để gạch xóa `<w:del>` đúng snippet sai và giữ nguyên vẹn phần còn lại của đoạn văn; (2) Pass 2 bổ sung trả về `noi_dung_sai` để thu hẹp chính xác cụm từ/vế câu vi phạm thay vì ôm cả đoạn; bổ sung unit test `test_de_xuat_rong_xoa_dung_snippet_giu_phan_con_lai`.
- 13/11/2026 — branch `feat/ai-agent`: sửa lỗi đề xuất sửa trùng lặp dự thảo và sửa định dạng căn cứ pháp lý: (1) gỡ bỏ regex ép xuống dòng Chương/Điều/Khoản/Điểm tránh ngắt vụn câu; giữ nguyên văn bản luật tự nhiên và cách dòng rõ ràng giữa căn cứ gốc và căn cứ tác động; (2) quy định rõ trong Pass 2 khi đoạn vi phạm tự đặt thêm ngoại lệ/trái luật cần bãi bỏ thì trả về `de_xuat_sua: ""` (UI tự hiện "Đề xuất: bỏ/loại phần nội dung vi phạm này"); bổ sung `la_de_xuat_trung_lap` và `la_de_xuat_menh_lenh_bo` trong `validate.py` để tự động lọc sạch.
- 13/11/2026 — branch `feat/ai-agent`: ẩn triệt để nội dung luật sửa đổi của LLM trên UI và DOCX: chỉ hiển thị căn cứ gốc và thông tin căn cứ tác động (nguồn sửa đổi/bãi bỏ); giữ khối nội dung sửa đổi cho LLM đối chiếu nội bộ; chuẩn hóa `tach_can_cu_goc` trong `validate.py`.
- 13/11/2026 — branch `feat/ai-agent`: tinh gọn comment DOCX track-changes (`_noi_dung_comment`): tách sạch 2 khối (căn cứ gốc đã lọc tiền tố kỹ thuật và căn cứ tác động sửa đổi/bãi bỏ), phân cách bằng 1 dòng trống kèm ghi chú `⚠ [vị_trí] đã được sửa đổi bởi [nguồn] (hiệu lực [ngày]):`; bổ sung unit tests.
- 13/11/2026 — branch `feat/ai-agent`: định dạng hiển thị căn cứ trên UI (`index.html`): tự động xuống dòng và thụt lề theo cấu trúc Chương, Điều, Khoản (1., 2...), Điểm (a, b...) và phân tách nhiều căn cứ (`---`).
- 13/11/2026 — branch `feat/ai-agent`: nâng cấp Pass 2 gom toàn bộ các căn cứ vi phạm trong 1 lượt gọi duy nhất mỗi đơn vị dự thảo (`can_cu_vi_pham_ids`), LLM suy luận tổng thể khắc phục đồng thời các vi phạm, bổ sung unit test `test_chay_tier2_multiple_violating_bases_single_call`.
- 13/11/2026 — branch `feat/ai-agent`: tách luồng audit thành cascade 2-pass (Pass 1 phân loại nhanh `think=False`, Pass 2 suy luận sâu `think=True` cho các mục vi phạm để sinh đề xuất sửa); bổ sung `prompt_tier2_de_xuat`, cập nhật `so_sanh.py`, test `test_so_sanh_cascade.py` và cập nhật tài liệu module.
- 13/11/2026 — branch `feat/ai-agent`: rà soát toàn bộ import và dependency trong `@app`, hoàn thiện `requirements.txt` và `pyproject.toml` (bổ sung `lxml`, `python-dotenv`, `PyYAML`; đồng bộ version pin theo `.venv` chuẩn).
- 13/11/2026 — branch `docs/agent-harness`: thêm tài liệu agent, `tasks.py`, kiểm tra tài liệu; cập nhật skill `.claude/skills/` theo cấu trúc hiện tại.
- 13/11/2026 — sửa crawl `doc_info` hỏng do vbpl đổi format (`</html>1:` → `</body>1:`), commit `8d5f10d`. 72 mục `crawl_queue` lỗi `Extra data…` cần reset `so_lan_thu` để crawl lại (mục đã đủ 3 lần thử sẽ không được `take_pending` lấy lại).

# app/doisanh — service đối sánh (kho RAG + API + UI)

**Trách nhiệm:** dựng kho luật dạng cây từ dữ liệu crawl, sinh embedding, và phục vụ API/UI: đối chiếu dự thảo (`/audit`), hỏi đáp (`/ask`), xem kho luật. Không gọi vbpl.vn.

**Giao diện với module khác**
- Chỉ import `app/core`. Đọc dữ liệu crawl từ DB (`vanban.document_cay`, `provision_impacts`, `document_content`), không import `app/crawl`.
- CLI: `python -m app.doisanh.cli build-cay [--embed]` rồi `port-impacts` ([cli.py](cli.py)).
- API: `uvicorn app.doisanh.api.main:app --port 8010`. Danh sách endpoint: [api/routes_simple.py](api/routes_simple.py). UI là một file [api/static/index.html](api/static/index.html), phục vụ ở `GET /`, `GET /audit`, `GET /legal` (trang HTML) — **trùng đường dẫn** với `POST /audit` (API) và khác `GET /api/legal` (JSON).

## Luồng chính (đang chạy)

```
build-cay:  document_cay ─► public_loader.save_cay ─► vanban.node (cây) + rag.chunk (chỉ node lá) ─► --embed
port-impacts: provision_impacts ─► vanban.tac_dong          (chạy SAU build-cay của cả VB nguồn lẫn đích)

/upload/draft: file ─► ingestion/loader ─► audit/segment ─► rag.du_thao + du_thao_node (+ embedding)
/audit:  mỗi đơn vị cấp khoản/điểm/đoạn, song song LLM_SONG_SONG luồng:
         retrieval/hybrid (SQL tim_kiem_hybrid: vector + BM25 + RRF, lọc hiệu lực theo ngày)
         ─► retrieval/rerank (TEI cross-encoder; lỗi/không cấu hình → giữ thứ tự RRF)
         ─► retrieval/can_cu (gộp anh em lên Khoản/Điều, dựng căn cứ + khối tác động sửa đổi)
         ─► audit/prompts.prompt_tier2_khoan ─► core.models.llm.goi_json
         ─► audit/so_sanh (chuẩn hóa verdict) + audit/validate (kiểm snippet, cắt đề xuất)
         ─► VI_PHAM / HOP_LE / CHUA_XAC_DINH   (/audit/docx: thêm DOCX track-change qua audit/docx_track)
/ask:    cùng retrieval ─► 1 lần gọi LLM (qa/chat) ─► câu trả lời có dẫn chiếu [n]
```

Số ứng viên ở mỗi tầng: `RERANK_LAY_VE`, `RERANK_TOP_N` trong `app/core/config.py`.

## Quyết định thiết kế và lý do

- **Chunk = node lá, `text_embed` kèm ngữ cảnh cha** (điểm chứa nội dung khoản, khoản chứa tên điều) → embedding không mất ngữ cảnh. Sau rerank mới **gộp lên** (≥2 điểm cùng khoản → cả khoản; ≥2 khoản cùng điều → cả điều; không leo quá Điều) để LLM nhận đơn vị pháp lý hoàn chỉnh. Test: `tests/test_nap_khoan_ung_vien.py`.
- **`node`/`chunk` là dữ liệu dẫn xuất**: `build-cay` xóa node của văn bản rồi dựng lại từ `document_cay`. Nguồn sự thật là bảng crawl. Dựng lại = phải embed lại các chunk đó.
- **Truy vấn retrieval bằng nội dung thuần của đơn vị**, không ghép tiêu đề cha: đo thực tế thấy tiêu đề kéo lệch lĩnh vực, giảm recall (comment trong `so_sanh.py`).
- **Căn cứ đã bị sửa/bãi bỏ**: nội dung sau sửa (`tac_dong`) được gắn vào đầu căn cứ để LLM so với bản hiện hành.
- Quy tắc phán quyết của LLM và kiểm tra đầu ra: [audit/CONSTRAINTS.md](audit/CONSTRAINTS.md).

## Mã di sản — đừng nhầm với luồng chính

Có hai đường audit. **Chỉ `routes_simple.py` → `audit/so_sanh.py` là đang chạy.** Các module sau viết cho schema v3 (`dieu_luat`/`khoan`, đã bị migration 003/012 drop); luồng chính không gọi tới, đừng sửa chúng để "fix" hành vi của `/audit`:

| Nhóm | Module |
|---|---|
| Workflow stateful (Điều ↔ Điều mẹ) | `audit/workflow.py`, `mapping.py`, `tier2.py`, `focus_khoan.py`, `parent_docs.py`, `consolidate.py`, `fallback.py`, `report.py`, `db/repo_audit.py`, `scripts/audit.py`, `scripts/eval_audit.py` |
| Nạp luật từ file | `ingestion/pipeline.py`, `amend_parser.py`, `summarize.py`, `chunks.py`, `sync.py`, `db/repo_van_ban.py`, `scripts/ingest.py`, `scripts/sync.py`, `scripts/seed_demo.py`, `scripts/embed_all.py` |
| Tắt bằng cờ (`ENABLE_TIER1=false`) | `audit/tier1.py`, `db/repo_hieu_luc.py`, `ingestion/citation_parser.py`, `ingestion/quan_he.py` |

`routes_simple.py` vẫn **import** `tier1.chay_tier1` và `ingestion.pipeline.nap_van_ban` (`/upload/legal`), nên xóa các module này sẽ làm vỡ API. **`POST /upload/legal` gần như chắc chắn hỏng**: nó đi qua `repo_van_ban`, ghi vào `dieu_luat`/`khoan` đã bị drop (suy từ SQL, chưa chạy thử). Nạp luật vào kho chỉ qua crawl → `build-cay`. Kế hoạch port hay xóa: TODO: cần xác nhận.

## Công cụ debug

`python tests/debug_retrieval.py "câu hỏi"` — in 40 chunk hybrid và căn cứ sau rerank, dùng đúng hàm của `/ask`. Cần DB + `EMBED_URL`.

---
name: legal-audit-workflow
description: Luồng đối chiếu dự thảo với kho pháp luật của audit-legal - upload/segment dự thảo, truy hồi lai + rerank + gộp căn cứ, prompt tier2 khoản cho LLM (Qwen chính), chuẩn hóa verdict VI_PHAM/HOP_LE/CHUA_XAC_DINH, kiểm snippet, đề xuất sửa, DOCX track-change, hỏi đáp /ask, eval. Dùng skill này mỗi khi làm việc trong app/doisanh/audit/, app/doisanh/retrieval/, app/doisanh/qa/, app/doisanh/api/routes_simple.py, scripts/eval_audit.py, khi viết hoặc sửa prompt, khi người dùng nói "đối chiếu", "audit", "phát hiện lỗi", "căn cứ pháp lý", "đề xuất sửa", "tier2", "prompt", "Qwen", "rerank", "truy hồi".
---

# Luồng đối chiếu dự thảo

Nguồn chính, đọc trước:
- [app/doisanh/ARCHITECTURE.md](../../../app/doisanh/ARCHITECTURE.md) — sơ đồ luồng `/upload/draft` → `/audit`, `/ask`, lý do thiết kế retrieval, danh sách module di sản.
- [app/doisanh/audit/CONSTRAINTS.md](../../../app/doisanh/audit/CONSTRAINTS.md) — hợp đồng JSON của LLM, quy tắc phán quyết, những gì **chưa** được kiểm.

## Sửa prompt (`audit/prompts.py::prompt_tier2_khoan`)

1. Đọc cả `TIER2_KHOAN_HE_THONG` lẫn khối `vi_du` — quy tắc nằm ở cả hai; thêm quy tắc mới thì thêm kèm 1 ví dụ ngắn đúng định dạng `[trang_thai - loai] ... -> ...`.
2. Không đổi tên khóa JSON trừ khi sửa đồng thời `so_sanh.chay_tier2`, `api/static/index.html`, `docx_track.py`.
3. Thử trên **Qwen local trước** (`is_local=true`, `think` mặc định tắt). Gửi cùng dự thảo mẫu trước và sau khi sửa, so 3 nhóm kết quả; ghi ca đã thử vào commit message hoặc `PROGRESS.md`.
4. `tests/audit/test_validate.py`, `test_segment.py`, `test_loai_rang_buoc.py` phải vẫn xanh (`python tasks.py check`).

## Sửa retrieval

- Tham số số lượng ở `app/core/config.py` (`RERANK_LAY_VE`, `RERANK_TOP_N`); SQL ở `migrations/007_ham_tim_kiem_hybrid.sql` (đổi = migration mới).
- Soi trước/sau bằng `python tests/debug_retrieval.py "<đoạn dự thảo>"`.
- Logic gộp anh em có test `tests/test_nap_khoan_ung_vien.py`; rerank tự lùi có `tests/test_rerank.py`.

## Eval

Chưa có cho luồng hiện tại. `scripts/eval_audit.py` và `references/vi-du-prompt.md` thuộc workflow di sản (mapping Điều ↔ Điều mẹ, tier1/tier2 theo Điều, bảng `phien_doi_chieu`) — không dùng làm mẫu cho `/audit` hiện tại. Kế hoạch bộ eval mới: [PROGRESS.md](../../../PROGRESS.md).

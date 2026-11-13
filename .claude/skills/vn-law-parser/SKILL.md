---
name: vn-law-parser
description: Cách parse văn bản quy phạm pháp luật Việt Nam thành Chương/Mục/Điều/Khoản/Điểm, nhận diện lệnh sửa đổi-bổ sung-bãi bỏ, trích dẫn chiếu ("khoản 2 Điều 54 Luật này"), phần Căn cứ, ngày hiệu lực, tóm tắt Điều, và quy tắc test. Dùng skill này mỗi khi làm việc trong app/doisanh/ingestion/ (parser.py, amend_parser.py, citation_parser.py, normalize.py, summarize.py, pipeline.py, loader.py), app/doisanh/audit/segment.py, khi viết regex cho văn bản luật, khi nạp file luật/nghị định/thông tư/dự thảo, hoặc khi người dùng hỏi về tách Điều, tách Khoản, dẫn chiếu, văn bản sửa đổi.
---

# Parse văn bản pháp luật Việt Nam

> **Trạng thái:** kho luật hiện **không** dựng bằng parser này mà từ cây JSON crawl của vbpl.vn (`app/doisanh/public_loader.py`). Parser text còn dùng trong luồng chính ở: `loader.py`, `normalize.py`, `parser.py` (qua `audit/segment.py` để cắt **dự thảo**). `amend_parser.py`, `summarize.py`, `pipeline.py`, `sync.py` là di sản ghi vào schema v3 đã drop (`dieu_luat`/`khoan`); `citation_parser.py` chỉ dùng khi bật `ENABLE_TIER1`. Các mục về ghi DB bên dưới mô tả hệ cũ.

Văn bản pháp luật có cấu trúc đều nhưng nhiều biến thể nhỏ (Điều 54a, "Điều 23." không tiêu đề, khoản lồng điểm, bảng biểu, trích ngoặc kép). Parser phải **không dừng khi gặp bất thường**: ghi WARNING kèm vị trí và đi tiếp; người dùng kiểm tra bằng số Điều kỳ vọng.

## Luồng và trách nhiệm

| Module | Vào → Ra | Không làm |
|---|---|---|
| `loader.py` | docx/pdf/txt/html → text thô, giữ `\n` | không chuẩn hóa |
| `normalize.py` | NFC, `Ð`→`Đ`, gộp khoảng trắng ngang, bỏ số trang/header lặp | không tách cấu trúc |
| `parser.py` | text → `VanBanMeta`, `list[Dieu]`, `list[Khoan]` | không ghi DB, không gọi LLM |
| `amend_parser.py` | `VanBanMeta` + Điều "Sửa đổi, bổ sung" → `list[LenhSuaDoi]` | không phân giải id, không chạm `dieu_luat`/`khoan` |
| `citation_parser.py` | text → `list[DanChieu]` (dạng thô) | không tra DB |
| `summarize.py` | `list[Dieu]` → `tom_tat` qua LLM, batch 20 | không chạy khi không có LLM (fallback tiêu đề + 120 ký tự) |
| `pipeline.py` | lắp ráp: loader → normalize → parser → repo; nếu `la_van_ban_sua_doi` → amend_parser → `ghi_lenh` | không thi hành lệnh (đó là `sync.py`) |

Mọi thứ trả về là pydantic trong `app/core/models/schemas.py` (segment trả dataclass riêng `DonViSegment`). Hàm parse là hàm thuần, test không cần DB.

## Regex cấu trúc (sau normalize, `re.MULTILINE`)

| Thành phần | Pattern | Ghi chú |
|---|---|---|
| Phần | `^Phần\s+(thứ\s+\w+\|[IVXLC]+)\.?\s*$` | hiếm |
| Chương | `^Chương\s+([IVXLC]+\|\d+)\.?\s*$` | tên ở dòng kế |
| Mục | `^Mục\s+(\d+)\.?\s*(.*)$` | |
| Điều | `^Điều\s+(\d+[a-zđ]?)\s*\.?\s*(.*)$` | `so_dieu` chuỗi; tiêu đề có thể rỗng |
| Khoản | `^(\d+[a-zđ]?)\.\s+` | trong thân Điều |
| Điểm | `^([a-zđ])\)\s+` | thuộc Khoản gần nhất |

Kiểm tra: số Điều tăng theo **phần số** (`54 → 54a → 55` hợp lệ; nhảy/trùng → WARNING có vị trí). Khoản bắt đầu từ 1 mỗi Điều; Điểm từ `a` mỗi Khoản.

Bẫy: dòng "1." bên trong ngoặc kép chưa đóng (nội dung mới của lệnh sửa đổi) hoặc trong bảng không phải Khoản. Quy tắc: theo dõi trạng thái ngoặc kép; chỉ nhận Khoản khi không ở trong ngoặc và dòng trước là tiêu đề Điều, Khoản/Điểm khác, hoặc dòng trống.

## Phần đầu văn bản (`VanBanMeta`)

- Số hiệu: `(\d+/\d{4}/(?:QH\d+|NĐ-CP|TT-[A-Z]+|NQ-[A-Z]+|QĐ-[A-Za-z]+))`; `loai` và `cap` suy từ hậu tố (QH→luật/bộ luật cấp 2, NĐ-CP→5, QĐ-TTg→6, TT→7).
- Cơ quan: dòng in hoa trước số hiệu (`QUỐC HỘI`, `CHÍNH PHỦ`, `BỘ ...`).
- Căn cứ: các dòng `^Căn cứ\s+` tới dòng trống hoặc "Theo đề nghị". Mỗi dòng → `CanCuTho(ten, so_hieu|None, nam|None)`. Khớp với `van_ban` là việc của `pipeline`/`parent_docs`, không của parser.
- Ngày hiệu lực: trong Điều "Hiệu lực thi hành": `có hiệu lực(?: thi hành)?(?: kể)? từ ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})`.
- `la_van_ban_sua_doi`: tên bắt đầu "Sửa đổi, bổ sung" hoặc có Điều tiêu đề khớp `Sửa đổi, bổ sung một số điều của (.+)`.
- Quan hệ ngầm: tên có "quy định chi tiết" / "hướng dẫn thi hành" + tên luật → pipeline ghi `quan_he_van_ban(loai='quy_dinh_chi_tiet')`; mỗi dòng Căn cứ → `loai='can_cu'`.

## Lệnh sửa đổi (`amend_parser.py`)

Văn bản đích = số hiệu trong tiêu đề Điều "Sửa đổi, bổ sung một số điều của ...". Mỗi Khoản của Điều đó là một lệnh. Pattern giữ trong một bảng `PATTERNS: list[tuple[LoaiLenh, re.Pattern]]` để thêm không sửa vòng lặp:

| loai | Pattern |
|---|---|
| sua_doi | `^Sửa đổi(?:, bổ sung)?\s+(?:điểm\s+([a-zđ])\s+)?(?:khoản\s+(\d+[a-zđ]?)\s+)?Điều\s+(\d+[a-zđ]?)\s+như sau:` |
| bo_sung | `^Bổ sung\s+(?:điểm\s+([a-zđ])\s+)?(?:khoản\s+(\d+[a-zđ]?)\s+)?(?:Điều\s+(\d+[a-zđ]?)\s+)?vào\s+(sau\|trước)\s+(?:điểm\s+[a-zđ]\s+)?(?:khoản\s+\d+[a-zđ]?\s+)?Điều\s+(\d+[a-zđ]?)\s+như sau:` |
| bai_bo | `^Bãi bỏ\s+(?:điểm\s+([a-zđ])\s+)?(?:khoản\s+(\d+[a-zđ]?)\s+)?Điều\s+(\d+[a-zđ]?)` (nhiều mục tách `,`/`và`) |
| thay_cum_tu | `^Thay(?: thế)? cụm từ\s+"(.+?)"\s+bằng cụm từ\s+"(.+?)"\s+tại\s+(.+)$` |

Nội dung mới = đoạn sau lệnh tới lệnh kế tiếp (trong ngoặc kép hoặc thụt đầu dòng). Không khớp pattern → `LenhSuaDoi(loai='sua_doi', noi_dung_moi=nguyên văn, tin_cay='can_ra_soat')` + WARNING. Không bỏ qua im lặng.

## Dẫn chiếu (`citation_parser.py`)

```
(?:điểm\s+(?P<diem>[a-zđ])\s+)?(?:khoản\s+(?P<khoan>\d+[a-zđ]?)\s+)?Điều\s+(?P<dieu>\d+[a-zđ]?)
\s+(?:của\s+)?(?P<vb>Luật này|Bộ luật này|Nghị định này|Thông tư này|[^.;,\n]+?(?:\d+/\d{4}/[\w-]+)?)
```

- "Luật này / Nghị định này" → `van_ban_id` hiện tại (parser nhận tham số `van_ban_hien_tai`).
- "các Điều 10, 12 và 15" → nhiều `DanChieu`. "Chương II", "Mục 3" → `so_dieu=None`, giữ `text_dan`.
- Trả thô; phân giải id và `ket_qua` là việc của `tier1`/`pipeline` qua `repo_hieu_luc`.

## Tài liệu không chuẩn (`audit/segment.py`)

Dùng cùng `parser.py`; không có Điều → tách đề mục `^[IVX]+\.`, `^\d+\.`, `^[a-zđ]\)`, cuối cùng theo đoạn (`cap='doan'`); > 30 đoạn → LLM gom `cum`. Ghi `tai_lieu.co_cau_truc_dieu`.

## Test

- Mỗi pattern ≥ 1 test dương + 1 test âm: `tests/test_parser.py`, `test_amend_parser.py`, `test_citation_parser.py`.
- Dữ liệu từ văn bản thật rút gọn trong `tests/data/`; **không tự chế nội dung luật dài**. Thiếu → dừng và hỏi.
- Nạp thật: số Điều phải khớp số người dùng cung cấp (BLLĐ 2019 = 220).
- Sửa regex vì văn bản mới → thêm ca tái hiện trước, rồi sửa, rồi chạy toàn bộ.

Ví dụ đầu vào/đầu ra từng pattern: `references/vi-du.md`.

---
name: clean-code-solid
description: Chuẩn code sạch và SOLID cho dự án audit-legal (Python 3.10+, FastAPI, psycopg, LLM qua HTTP) - ranh giới module giữa core/crawl/doisanh, dependency injection cho DB/LLM, pydantic model, xử lý lỗi, logging, test với mock, quy ước đặt tên. Luôn dùng skill này khi viết hoặc sửa bất kỳ file Python nào trong app/, scripts/, tests/, khi review code, khi thiết kế module mới, hoặc khi người dùng nhắc "code sạch", "SOLID", "refactor", "tách hàm", "đổi tên", "viết test".
---

# Code sạch và SOLID trong audit-legal

> Trạng thái: phần lớn code hiện tại (đặc biệt `audit/so_sanh.py`, `api/routes_simple.py`) **chưa** theo hết các quy tắc dưới đây — chúng là đích hướng tới cho code mới và code đang sửa, không phải mô tả hiện trạng. Ranh giới cứng và lệnh kiểm tra: [AGENTS.md](../../../AGENTS.md).

Hai service `app/crawl` và `app/doisanh` dùng chung `app/core`; không import lẫn nhau. Trong `app/doisanh`: `db/` (repo SQL) → `ingestion/`, `retrieval/`, `audit/`, `qa/` (nghiệp vụ) → `api/`, `cli.py`, `scripts/` (giao diện). Phụ thuộc chỉ đi **xuống**.

## Kiến trúc và ranh giới

| Tầng | Được import | Không được import |
|---|---|---|
| `app/core/` (config, db/session, models/llm, embedder, schemas) | `httpx`, `psycopg`, `pydantic` | `app/crawl`, `app/doisanh` |
| `app/doisanh/db/` | `core` | `ingestion`, `audit`, `api`, `core/models/llm` |
| `app/doisanh/{ingestion,retrieval,audit,qa}/` | `core`, `doisanh/db` | `api`, `scripts` |
| `app/doisanh/api/`, `cli.py`, `scripts/` | tất cả trong cùng service | service kia |

- SQL mới nên nằm trong repo (`app/doisanh/db/repo_*.py`, `app/crawl/store.py`). Hiện `retrieval/` vẫn gọi SQL trực tiếp — chấp nhận, không lan thêm.
- Gọi LLM **chỉ** qua `app/core/models/llm.py` (`goi_json` cho đầu ra JSON, `goi_chat` cho văn bản). Prompt nằm trong `prompts.py` của module dùng nó, dạng hàm trả `list[{"role","content"}]`.
- `config.settings` chỉ đọc ở tầng giao diện và ở nơi khởi tạo client; hàm nghiệp vụ mới nhận tham số, không đọc `settings` bên trong.

## SOLID áp vào dự án

**S – mỗi module một lý do để thay đổi.** `segment.py` chỉ biết tách tài liệu; `parent_docs.py` chỉ biết chọn văn bản mẹ; `tier1.py` chỉ biết kiểm tra xác định. Hàm nào vừa parse vừa ghi DB vừa gọi LLM là sai; tách thành parse → model → repo.

**O – mở rộng bằng cách thêm, không sửa.** Mẫu regex mới (cấu trúc văn bản, loại ràng buộc sàn/trần, lệnh sửa đổi) = thêm vào bảng pattern, không thêm nhánh `if` vào vòng lặp.

**L – thay thế được.** Hàm nghiệp vụ mới nhận "hàm gọi LLM" (cùng chữ ký `goi_json`) làm tham số, để test truyền hàm giả trả JSON cố định; tương tự với hàm đọc DB. Code nghiệp vụ không được biết nó đang dùng bản nào.

**I – giao diện nhỏ.** `tier2.py` cần "gọi LLM trả JSON" và "lấy Điều mẹ theo id"; nó nhận hai hàm/đối tượng đó, không nhận cả `Settings` hay cả `AuditRepo` với 30 phương thức. Định nghĩa `Protocol` nhỏ ngay tại module dùng:

```python
class LLMJson(Protocol):
    def chat_json(self, system: str, user: str, schema_hint: str) -> list | dict: ...

class DieuMeReader(Protocol):
    def lay_dieu_full(self, dieu_id: str, ngay: date) -> DieuFull: ...
```

**D – phụ thuộc đi qua tham số.** Mọi bước audit là hàm thuần hoặc lớp nhận phụ thuộc trong `__init__`:

```python
def anh_xa_dieu(muc_luc_du_thao: list[MucLucDonVi], muc_luc_me: list[MucLucDieu],
                llm: LLMJson, max_dieu_me: int) -> list[AnhXa]:
```

Lắp ráp (wiring) chỉ ở `api/`, `cli.py`, `scripts/*.py`. Không `global`, không singleton ngầm ngoài `settings` và connection pool.

## Dữ liệu và kiểu

- Mọi cấu trúc trao đổi giữa module là `pydantic.BaseModel` trong `app/core/models/schemas.py` (hiện có `VanBanMeta`, `Dieu`, `Khoan`). Luồng audit hiện truyền `dict` (ứng viên căn cứ, verdict) — code mới không mở rộng kiểu đó.
- Tập giá trị cố định (`loai_loi`, `trang_thai`, `nguon`) là `enum.StrEnum` dùng chung giữa Python và DB; không rải chuỗi literal trong code.
- Đầu ra LLM: parse → `pydantic.TypeAdapter(list[...]).validate_python` → validate nghiệp vụ (id có trong input, trích dẫn khớp). Thất bại → ném lỗi có lý do (họ `LoiLLM`), không `except: pass`.
- Hàm trả về giá trị, không in; `scripts/` mới in bằng `rich`.
- Type hints đầy đủ; `from __future__ import annotations`; `Optional` viết `X | None`.

## Hàm và tên

- Hàm ≤ ~40 dòng, một mức trừu tượng. Vòng lặp lớn có thân phức tạp → tách hàm có tên.
- **Tên tiếng Anh** (quyết định 13/11/2026: chuyển toàn bộ codebase sang tiếng Anh). Code mới viết tiếng Anh; code cũ tiếng Việt không dấu (`ket_noi`, `tim_hybrid`) chỉ đổi trong đợt đổi tên theo module (xem `PROGRESS.md`), không đổi lẻ tẻ khi sửa việc khác. Cách gọi thuật ngữ pháp lý (Điều/Khoản/Điểm → `article`/`clause`/`point` hay giữ `dieu`/`khoan`/`diem`): TODO: cần xác nhận. Không trộn hai ngôn ngữ trong một tên.
- Boolean đặt tên khẳng định (`is_…`, `has_…`); không `not_found`.
- Không viết tắt mơ hồ (`vb`, `dv`) ngoài phạm vi 5 dòng.
- Không comment giải thích "cái gì" (code đã nói); comment chỉ cho "tại sao" (một quy tắc pháp lý, một quyết định thiết kế). Docstring một dòng cho hàm public.

## Lỗi và log

- Lỗi LLM hiện có: `LoiLLM`, `LoiParseJSON` trong `app/core/models/llm.py`. Chưa có module lỗi chung; khi cần lớp lỗi mới, đặt cạnh module ném nó. API map sang mã HTTP tại `api/`, không raise `HTTPException` trong nghiệp vụ.
- Parser gặp bất thường: **ghi WARNING kèm vị trí, đi tiếp**, không raise (quy tắc riêng của parse luật).
- Log bằng `logging` chuẩn (`logger = logging.getLogger(__name__)`); `structlog` có trong `pyproject.toml` nhưng code không dùng. Kèm id liên quan (`don_vi`, `van_ban_id`) trong message. Log ở ranh giới (bắt đầu/kết thúc bước, lỗi), không log từng dòng vòng lặp.
- Không `print` trong `app/`.

## Test

- Mỗi module nghiệp vụ có `tests/test_<module>.py` viết cùng commit. Test không cần DB và không cần LLM chạy mặc định; test cần DB `@pytest.mark.integration`, cần LLM `@pytest.mark.llm`, bỏ qua khi thiếu `DB_URL`/`LLM_URL`.
- Chưa có `tests/conftest.py`; giả LLM/DB bằng `monkeypatch` hoặc truyền hàm giả qua tham số (xem `tests/test_rerank.py`).
- Test đặt tên theo hành vi: `test_bai_bo_khoan_khong_tao_phien_ban_moi`, `test_anh_xa_loai_id_khong_co_trong_input`.
- Dữ liệu test là văn bản thật rút gọn trong `tests/data/`; không tự chế luật dài.
- Sửa lỗi → thêm test tái hiện trước, rồi sửa.

## Trước khi commit

- [ ] Không có SQL ngoài `db/`, không gọi LLM ngoài `models/llm.py`.
- [ ] Hàm mới nhận phụ thuộc qua tham số; không đọc `settings` trong nghiệp vụ.
- [ ] Giá trị cố định dùng Enum; dữ liệu qua ranh giới là pydantic.
- [ ] Có test; `python tasks.py check` xanh (dự án không dùng ruff — đã quyết định).
- [ ] Không thêm thư viện ngoài `requirements.txt` khi chưa hỏi người dùng.

Ví dụ minh họa cách tách bước + inject phụ thuộc: `references/vi-du-tier1.md` (đường dẫn `app/audit/tier1/...` trong ví dụ là cấu trúc cũ, không tồn tại).

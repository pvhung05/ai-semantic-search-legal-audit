---
name: clean-code-solid
description: Chuẩn code sạch và SOLID cho dự án audit_rag (Python 3.10+, FastAPI, psycopg, LLM qua HTTP) - ranh giới module, dependency injection cho DB/LLM, pydantic model, xử lý lỗi, logging, test với mock. Luôn dùng skill này khi viết hoặc sửa bất kỳ file Python nào trong app/, scripts/, tests/, khi review code, khi thiết kế module mới, hoặc khi người dùng nhắc "code sạch", "SOLID", "refactor", "tách hàm", "viết test".
---

# Code sạch và SOLID trong audit_rag

Dự án có ba tầng: `db/` (kho và hàm SQL) → `ingestion/`, `audit/` (nghiệp vụ) → `api/`, `scripts/` (giao diện). Phụ thuộc chỉ đi **xuống**. Mọi quy tắc dưới đây nhằm giữ ba tầng đó tách biệt để từng phần test được, thay được và Claude Code sửa được mà không làm vỡ phần khác.

## Kiến trúc và ranh giới

| Tầng | Được import | Không được import |
|---|---|---|
| `app/db/` | `psycopg`, `models/schemas` | `ingestion`, `audit`, `api`, `models/llm` |
| `app/ingestion/`, `app/audit/` | `db`, `models/*` | `api`, `scripts` |
| `app/api/`, `scripts/` | tất cả | — |
| `app/models/` (schemas, llm, embedder) | `httpx`, `pydantic`, `config` | `db`, `audit` |

- SQL **chỉ** nằm trong `app/db/repo_*.py`. Module nghiệp vụ gọi hàm repo có tên nghiệp vụ (`lay_ban_hop_nhat`, `ghi_phat_hien`), không ghép chuỗi SQL.
- Gọi LLM **chỉ** qua `models/llm.py` (`LLMClient.chat_json(...)`). Prompt nằm trong `prompts.py` của module dùng nó, dạng hàm trả chuỗi (`prompt_anh_xa(muc_luc_du_thao, muc_luc_me) -> str`).
- `config.settings` chỉ đọc ở tầng giao diện và ở nơi khởi tạo client; hàm nghiệp vụ nhận tham số, không đọc `settings` bên trong.

## SOLID áp vào dự án

**S – mỗi module một lý do để thay đổi.** `segment.py` chỉ biết tách tài liệu; `parent_docs.py` chỉ biết chọn văn bản mẹ; `tier1.py` chỉ biết kiểm tra xác định. Hàm nào vừa parse vừa ghi DB vừa gọi LLM là sai; tách thành parse → model → repo.

**O – mở rộng bằng cách thêm, không sửa.** Loại lỗi mới (`loai_loi`) = thêm một `Checker` trong `tier1/checks/` và đăng ký vào danh sách, không sửa hàm `kiem_tra_tang1`. Nguồn xác định văn bản mẹ mới = thêm một `NguonVanBanMe`, không thêm nhánh `if`. Pattern lệnh sửa đổi mới = thêm vào bảng pattern, không sửa vòng lặp.

**L – thay thế được.** `LLMClient` thật và `FakeLLM` (trả JSON cố định) cùng giao diện `chat_json`; repo thật và repo in-memory cùng giao diện trong test. Code nghiệp vụ không được biết nó đang dùng bản nào.

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

Lắp ráp (wiring) chỉ ở `audit/workflow.py`, `api/main.py`, `scripts/*.py`. Không `global`, không singleton ngầm ngoài `settings` và connection pool.

## Dữ liệu và kiểu

- Mọi cấu trúc trao đổi giữa module là `pydantic.BaseModel` trong `models/schemas.py` (`VanBanMeta`, `Dieu`, `Khoan`, `LenhSuaDoi`, `DanChieu`, `DonVi`, `AnhXa`, `PhatHien`). Không truyền `dict` thô qua ranh giới module.
- Tập giá trị cố định (`loai_loi`, `trang_thai`, `nguon`) là `enum.StrEnum` dùng chung giữa Python và DB; không rải chuỗi literal trong code.
- Đầu ra LLM: parse → `pydantic.TypeAdapter(list[...]).validate_python` → validate nghiệp vụ (id có trong input, trích dẫn khớp). Thất bại → `LLMOutputError` với lý do, không `except: pass`.
- Hàm trả về giá trị, không in; `scripts/` mới in bằng `rich`.
- Type hints đầy đủ; `from __future__ import annotations`; `Optional` viết `X | None`.

## Hàm và tên

- Hàm ≤ ~40 dòng, một mức trừu tượng. Vòng lặp lớn có thân phức tạp → tách hàm có tên.
- Tên tiếng Việt không dấu cho nghiệp vụ pháp lý (`lay_ban_hop_nhat`, `kiem_tra_dan_chieu`), tiếng Anh cho kỹ thuật chung (`retry`, `batch`, `parse_json`). Không trộn trong một tên.
- Boolean đặt tên khẳng định: `co_cau_truc_dieu`, `da_ap_dung`; không `not_found`.
- Không viết tắt mơ hồ (`vb`, `dv`) ngoài phạm vi 5 dòng.
- Không comment giải thích "cái gì" (code đã nói); comment chỉ cho "tại sao" (một quy tắc pháp lý, một quyết định thiết kế). Docstring một dòng cho hàm public.

## Lỗi và log

- Lớp lỗi riêng trong `app/errors.py`: `ParseError`, `LLMOutputError`, `HieuLucError`, `AuditStateError`. API map sang mã HTTP tại `api/`, không raise `HTTPException` trong nghiệp vụ.
- Parser gặp bất thường: **ghi WARNING kèm vị trí, đi tiếp**, không raise (quy tắc riêng của parse luật).
- `structlog` với key cố định: `van_ban_id`, `dieu_id`, `phien_id`, `buoc`, `so_goi_llm`. Log ở ranh giới (bắt đầu/kết thúc bước, lỗi), không log từng dòng vòng lặp.
- Không `print` trong `app/`.

## Test

- Mỗi module nghiệp vụ có `tests/test_<module>.py` viết cùng commit. Test không cần DB và không cần LLM chạy mặc định; test cần DB `@pytest.mark.integration`, cần LLM `@pytest.mark.llm`, bỏ qua khi thiếu `DB_URL`/`LLM_URL`.
- `tests/conftest.py` cung cấp `fake_llm(responses: dict[str, Any])` trả JSON cố định theo khóa prompt, và `mem_repo()` in-memory cho repo đọc.
- Test đặt tên theo hành vi: `test_bai_bo_khoan_khong_tao_phien_ban_moi`, `test_anh_xa_loai_id_khong_co_trong_input`.
- Dữ liệu test là văn bản thật rút gọn trong `tests/data/`; không tự chế luật dài.
- Sửa lỗi → thêm test tái hiện trước, rồi sửa.

## Trước khi commit

- [ ] Không có SQL ngoài `db/`, không gọi LLM ngoài `models/llm.py`.
- [ ] Hàm mới nhận phụ thuộc qua tham số; không đọc `settings` trong nghiệp vụ.
- [ ] Giá trị cố định dùng Enum; dữ liệu qua ranh giới là pydantic.
- [ ] Có test; `pytest -m "not integration and not llm"` xanh; `ruff check` và `ruff format` sạch (cấu hình trong `pyproject.toml`: line-length 100, rules `E,F,I,B,UP`).
- [ ] Không thêm thư viện ngoài danh sách PLAN.md mục 9.

Ví dụ cấu trúc một bước audit viết đúng chuẩn: `references/vi-du-tier1.md`.

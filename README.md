# audit-legal

Service doi chieu van ban du thao voi kho phap luat Viet Nam.
Chi tiet kien truc va ke hoach xem `PLAN.md` (v3). Huong dan cho Claude Code o `CLAUDE.md`.

## Khoi tao

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -e ".[dev]"
cp .env.example .env           # chinh sua neu can
python scripts/init_db.py      # sau khi co migrations/001_init.sql (task A2)
```

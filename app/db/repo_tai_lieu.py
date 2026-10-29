"""Repository tai_lieu + tai_lieu_don_vi + dan_chieu cua tai lieu."""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from psycopg import Connection

from app.config import settings


def sinh_id_tai_lieu() -> str:
    return "TL-" + uuid.uuid4().hex[:8]


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def luu_file(path: Path, tai_lieu_id: str) -> str:
    """Chep file vao STORAGE_PATH, tra storage_key."""
    storage_dir = Path(settings.STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)
    key = f"{tai_lieu_id}{path.suffix.lower()}"
    dest = storage_dir / key
    dest.write_bytes(path.read_bytes())
    return key


def tao_tai_lieu(
    conn: Connection,
    tai_lieu_id: str,
    ten: str,
    loai: str,
    cap_tuong_duong: int | None,
    ngay_du_kien: date | None,
    linh_vuc: list[str],
    can_cu_tho: list[str],
    co_cau_truc_dieu: bool,
    storage_key: str | None = None,
    file_hash: str | None = None,
    owner_id: str = "demo",
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO tai_lieu (
                 id, owner_id, ten, loai, cap_tuong_duong, ngay_du_kien,
                 linh_vuc, can_cu_tho, co_cau_truc_dieu, storage_key, hash
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 ten=EXCLUDED.ten, loai=EXCLUDED.loai,
                 cap_tuong_duong=EXCLUDED.cap_tuong_duong,
                 ngay_du_kien=EXCLUDED.ngay_du_kien,
                 linh_vuc=EXCLUDED.linh_vuc,
                 can_cu_tho=EXCLUDED.can_cu_tho,
                 co_cau_truc_dieu=EXCLUDED.co_cau_truc_dieu,
                 storage_key=EXCLUDED.storage_key, hash=EXCLUDED.hash""",
            (tai_lieu_id, owner_id, ten, loai, cap_tuong_duong, ngay_du_kien,
             linh_vuc, can_cu_tho, co_cau_truc_dieu, storage_key, file_hash),
        )
    return tai_lieu_id


def luu_don_vi(conn: Connection, don_vi: dict[str, Any]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO tai_lieu_don_vi (
                 id, tai_lieu_id, parent_id, cap, so_dieu, so_khoan, diem, tieu_de,
                 noi_dung, hash, thu_tu
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 parent_id=EXCLUDED.parent_id, cap=EXCLUDED.cap,
                 so_dieu=EXCLUDED.so_dieu, so_khoan=EXCLUDED.so_khoan,
                 diem=EXCLUDED.diem, tieu_de=EXCLUDED.tieu_de,
                 noi_dung=EXCLUDED.noi_dung, hash=EXCLUDED.hash,
                 thu_tu=EXCLUDED.thu_tu""",
            (don_vi["id"], don_vi["tai_lieu_id"], don_vi.get("parent_id"),
             don_vi["cap"], don_vi.get("so_dieu"), don_vi.get("so_khoan"),
             don_vi.get("diem"), don_vi.get("tieu_de"),
             don_vi["noi_dung"], don_vi["hash"], don_vi["thu_tu"]),
        )
    return don_vi["id"]


def danh_sach_don_vi(conn: Connection, tai_lieu_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, parent_id, cap, so_dieu, so_khoan, diem, tieu_de, noi_dung, hash, thu_tu
               FROM tai_lieu_don_vi WHERE tai_lieu_id=%s ORDER BY thu_tu""",
            (tai_lieu_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

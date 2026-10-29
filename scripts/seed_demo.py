"""Seed bo du lieu demo + seed chu_de_van_ban_me.

Doc config tu scripts/seed_demo.yaml (ban cung cap). Vi tri file hoac cot
'chu_de' lam goi y van ban me cho tung loai tai lieu/linh vuc.

Khong co YAML -> van hoat dong voi JSON tuong duong.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.session import ket_noi  # noqa: E402
from app.ingestion.pipeline import nap_van_ban  # noqa: E402
from app.ingestion.sync import dong_bo_hieu_luc  # noqa: E402
from app.models.schemas import VanBanMeta  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("Chua cai pyyaml. Dung .json hoac pip install pyyaml") from exc
        return yaml.safe_load(text)
    return json.loads(text)


def seed(config_path: Path) -> None:
    cfg = _load_config(config_path)
    for item in cfg.get("van_ban", []):
        meta = VanBanMeta(**{k: v for k, v in item.items() if k != "file"})
        if isinstance(meta.ngay_ban_hanh, str):
            meta = meta.model_copy(update={"ngay_ban_hanh": date.fromisoformat(meta.ngay_ban_hanh)})
        kq = nap_van_ban(Path(item["file"]), meta, hieu_luc_tu=meta.ngay_hieu_luc)
        print(" nap", meta.id, kq)
    print("dong bo hieu luc...")
    dong_bo_hieu_luc()
    with ket_noi() as conn, conn.cursor() as cur:
        for row in cfg.get("chu_de_van_ban_me", []):
            cur.execute(
                "INSERT INTO chu_de_van_ban_me (loai_tai_lieu, linh_vuc, van_ban_id) "
                "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (row["loai_tai_lieu"], row["linh_vuc"], row["van_ban_id"]),
            )
        conn.commit()
    print("seed xong")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    seed(p.parse_args().config)

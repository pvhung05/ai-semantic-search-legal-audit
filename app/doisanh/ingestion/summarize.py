"""Tom tat moi Dieu luat thanh 1 cau <= 30 tu, batch 20 Dieu/prompt.

Khong co LLM -> fallback: tieu_de + 120 ky tu dau noi_dung.
"""
from __future__ import annotations

import logging
from typing import Callable

from app.core.models.llm import LoiLLM, goi_json
from app.core.models.schemas import Dieu

logger = logging.getLogger(__name__)

PROMPT_HE_THONG = (
    "Ban la chuyen vien tham dinh van ban. Tom tat moi Dieu luat thanh MOT cau <= 30 tu, "
    "neu doi tuong va noi dung chinh, khong neu so Dieu. Chi tra JSON."
)


def _prompt_batch(dieu_batch: list[Dieu]) -> list[dict[str, str]]:
    items = [
        {
            "dieu_id": d.so_dieu,
            "tieu_de": d.tieu_de or "",
            "noi_dung": d.noi_dung[:2000],
        }
        for d in dieu_batch
    ]
    return [
        {"role": "system", "content": PROMPT_HE_THONG},
        {
            "role": "user",
            "content": (
                "Tra ve JSON mang [{dieu_id, tom_tat}]. Khong giai thich. "
                "Danh sach Dieu:\n" + str(items)
            ),
        },
    ]


def _tom_tat_fallback(dieu: Dieu) -> str:
    tieu_de = (dieu.tieu_de or "").strip()
    noi_dung = dieu.noi_dung.replace("\n", " ").strip()[:120]
    return (tieu_de + ". " + noi_dung).strip(". ").strip()


def tom_tat_dieu(
    dieu_list: list[Dieu],
    batch_size: int = 20,
    goi_json_fn: Callable[..., object] = goi_json,
) -> list[Dieu]:
    """Dien tom_tat vao moi Dieu; batch 20 Dieu/prompt. Loi -> fallback."""
    for i in range(0, len(dieu_list), batch_size):
        batch = dieu_list[i : i + batch_size]
        try:
            data = goi_json_fn(_prompt_batch(batch))
            if not isinstance(data, list):
                raise LoiLLM("Phan hoi khong phai mang")
            map_tom_tat = {str(item.get("dieu_id")): item.get("tom_tat", "") for item in data}
            for d in batch:
                tt = (map_tom_tat.get(d.so_dieu) or "").strip()
                d.tom_tat = tt or _tom_tat_fallback(d)
        except Exception as exc:
            logger.warning("Tom tat batch that bai, dung fallback: %s", exc)
            for d in batch:
                d.tom_tat = _tom_tat_fallback(d)
    return dieu_list

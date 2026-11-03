"""Client HTTP OpenAI-compatible cho embedding (vd Ollama bge-m3)."""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def embed_batch(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Tao embedding cho mot batch text."""
    if not texts:
        return []
    body = {"model": model or settings.EMBED_MODEL, "input": texts}
    with httpx.Client(timeout=120) as cli:
        resp = cli.post(
            f"{settings.EMBED_URL}/embeddings",
            headers={"Authorization": f"Bearer {settings.EMBED_API_KEY}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    return [d["embedding"] for d in data["data"]]


def embed(text: str) -> list[float]:
    out = embed_batch([text])
    return out[0] if out else []

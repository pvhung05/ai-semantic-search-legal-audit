"""Client HTTP OpenAI-compatible cho LLM (vd Ollama).

- Retry 3 lan voi backoff
- Tat thinking neu LLM_DISABLE_THINKING=true (chen 'nothink' theo Qwen3)
- Cat ``` truoc parse JSON
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

RE_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LoiLLM(Exception):
    pass


class LoiParseJSON(LoiLLM):
    pass


def _lam_sach_json(text: str) -> str:
    """Cat markdown code fence truoc khi parse."""
    text = text.strip()
    text = RE_CODE_FENCE.sub("", text)
    # cat <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def goi_chat(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
    is_local: bool | None = None,
) -> str:
    """Goi /chat/completions, tra noi dung dong 1.

    is_local: None -> dung IS_LOCAL mac dinh; true -> Qwen local; false -> Gemini.
    """
    url, model_mac_dinh, api_key = settings.cau_hinh_llm(is_local)
    body: dict[str, Any] = {
        "model": model or model_mac_dinh,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
        "stream": False,
    }
    # 'chat_template_kwargs' chi dung cho Ollama/vLLM (Qwen3). Gemini/OpenAI khong chap nhan.
    if settings.LLM_DISABLE_THINKING and "googleapis.com" not in url:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if extra:
        body.update(extra)
    with httpx.Client(timeout=120) as cli:
        resp = cli.post(
            f"{url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise LoiLLM(f"Phan hoi LLM khong hop le: {data}") from exc


def goi_json(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    retry_khi_loi_parse: bool = True,
    is_local: bool | None = None,
) -> Any:
    """Goi LLM, parse JSON tu phan hoi. Retry 1 lan neu loi parse."""
    raw = goi_chat(messages, temperature=temperature, max_tokens=max_tokens, is_local=is_local)
    try:
        return json.loads(_lam_sach_json(raw))
    except json.JSONDecodeError as exc:
        if not retry_khi_loi_parse:
            raise LoiParseJSON(f"Parse JSON that bai: {exc}\n{raw[:500]}") from exc
        them = {
            "role": "user",
            "content": (
                f"Phan hoi truoc KHONG phai JSON hop le ({exc.msg}). "
                "Hay tra lai CHI JSON, khong kem markdown fence hoac giai thich."
            ),
        }
        raw2 = goi_chat(messages + [{"role": "assistant", "content": raw}, them],
                        temperature=temperature, max_tokens=max_tokens, is_local=is_local)
        try:
            return json.loads(_lam_sach_json(raw2))
        except json.JSONDecodeError as exc2:
            raise LoiParseJSON(
                f"Parse JSON that bai (lan 2): {exc2}\n{raw2[:500]}"
            ) from exc2

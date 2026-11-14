"""Client HTTP cho LLM.

- Local (Ollama): goi endpoint NATIVE /api/chat de tat thinking THAT bang `think:false`
  va dat `num_ctx` (endpoint /v1 OpenAI-compat BO QUA ca hai -> da kiem chung).
- Cloud (Gemini/Claude): endpoint /v1 OpenAI-compatible, Bearer auth.
- Retry 3 lan voi backoff. Cat ``` truoc parse JSON.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

RE_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_CLIENT: httpx.Client | None = None


def _lay_client() -> httpx.Client:
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.Client(timeout=120)
    return _CLIENT


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
    think: bool | None = None,
) -> str:
    """Goi /chat/completions, tra noi dung dong 1.

    is_local: None -> dung IS_LOCAL mac dinh; true -> Qwen local; false -> Claude.
    think: chi model local; None -> theo LLM_DISABLE_THINKING (.env).
    """
    dung_local = settings.IS_LOCAL if is_local is None else is_local
    url, model_mac_dinh, api_key = settings.cau_hinh_llm(is_local)
    api_key = (api_key or "").strip()
    if not api_key:
        raise LoiLLM(
            "Thieu API key cho LLM (is_local=%s). Dat LOCAL_LLM_API_KEY / "
            "GEMINI_LLM_API_KEY trong .env roi khoi dong lai service." % dung_local
        )
    temp = settings.LLM_TEMPERATURE if temperature is None else temperature
    max_tok = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
    model_dung = model or model_mac_dinh

    if dung_local:
        # Ollama NATIVE /api/chat: think=false tat thinking THAT; options.num_ctx an dinh context.
        # (Endpoint /v1 bo qua ca `think`/`enable_thinking` lan `num_ctx` -> da kiem chung.)
        base = url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        body: dict[str, Any] = {
            "model": model_dung,
            "messages": messages,
            "stream": False,
            "think": (not settings.LLM_DISABLE_THINKING) if think is None else think,
            "options": {
                "temperature": temp,
                "num_predict": max_tok,
                "num_ctx": settings.LLM_NUM_CTX,
            },
        }
        if extra:
            body.update(extra)
        cli = _lay_client()
        resp = cli.post(f"{base}/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["message"]["content"] or ""
        except KeyError as exc:
            raise LoiLLM(f"Phan hoi Ollama khong hop le: {data}") from exc

    # Cloud (Gemini/Claude) qua endpoint OpenAI-compatible /v1.
    body = {
        "model": model_dung,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tok,
        "stream": False,
    }
    if extra:
        body.update(extra)
    cli = _lay_client()
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
    think: bool | None = None,
) -> Any:
    """Goi LLM, parse JSON tu phan hoi. Retry 1 lan neu loi parse."""
    raw = goi_chat(messages, temperature=temperature, max_tokens=max_tokens, is_local=is_local, think=think)
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
                        temperature=temperature, max_tokens=max_tokens, is_local=is_local, think=think)
        try:
            return json.loads(_lam_sach_json(raw2))
        except json.JSONDecodeError as exc2:
            raise LoiParseJSON(
                f"Parse JSON that bai (lan 2): {exc2}\n{raw2[:500]}"
            ) from exc2

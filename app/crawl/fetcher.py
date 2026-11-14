"""HTTP client cho vbpl.vn: GET detail + POST Server Action.

Giu rate limit tuan tu 1.5-3.5s, retry voi backoff. Khong song song hoa."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

BASE = "https://vbpl.vn"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True)
class FetchConfig:
    delay_min: float = 1.5
    delay_max: float = 3.5
    timeout: int = 30
    max_retry: int = 3
    retry_backoff: int = 5
    cool_down_429: int = 30


class ActionError(RuntimeError):
    """Server Action tra ve status khac 200 - co the ID da doi."""


def _cfg_tu_settings() -> FetchConfig:
    """FetchConfig mac dinh lay delay tu .env (CRAWL_DELAY_MIN/MAX)."""
    from app.core.config import settings
    return FetchConfig(delay_min=settings.CRAWL_DELAY_MIN, delay_max=settings.CRAWL_DELAY_MAX)


class Fetcher:
    def __init__(self, cfg: FetchConfig | None = None) -> None:
        self.cfg = cfg or _cfg_tu_settings()
        self.s = httpx.Client(headers=_DEFAULT_HEADERS, timeout=self.cfg.timeout)

    def _sleep(self) -> None:
        time.sleep(random.uniform(self.cfg.delay_min, self.cfg.delay_max))

    def get(self, url: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.cfg.max_retry + 1):
            self._sleep()
            try:
                r = self.s.get(url, timeout=self.cfg.timeout)
                if r.status_code in (429, 503):
                    wait = self.cfg.cool_down_429 * attempt
                    log.warning("GET %s -> %s, cho %ss", url, r.status_code, wait)
                    time.sleep(wait)
                    continue
                r.encoding = "utf-8"
                return r
            except httpx.HTTPError as e:
                last_exc = e
                log.warning("GET %s loi (lan %d/%d): %s",
                            url, attempt, self.cfg.max_retry, e)
                time.sleep(self.cfg.retry_backoff * attempt)
        raise RuntimeError(f"GET {url} that bai") from last_exc

    def rsc(self, action_id: str, body: str, referer: str = BASE + "/") -> httpx.Response:
        headers = {
            "Next-Action": action_id,
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "text/x-component",
            "Referer": referer,
            "Origin": BASE,
        }
        last_exc: Exception | None = None
        for attempt in range(1, self.cfg.max_retry + 1):
            self._sleep()
            try:
                r = self.s.post(BASE + "/", headers=headers,
                                content=body.encode("utf-8"), timeout=self.cfg.timeout)
                r.encoding = "utf-8"
                if r.status_code == 200:
                    return r
                if r.status_code in (400, 404):
                    raise ActionError(
                        f"Server Action {action_id} tra ve {r.status_code} "
                        "- co the ID da doi, can sniff lai"
                    )
                if r.status_code in (429, 503):
                    wait = self.cfg.cool_down_429 * attempt
                    log.warning("RSC %s -> %s, cho %ss", action_id, r.status_code, wait)
                    time.sleep(wait)
                    continue
                log.warning("RSC %s -> %s (lan %d/%d)",
                            action_id, r.status_code, attempt, self.cfg.max_retry)
            except ActionError:
                raise
            except httpx.HTTPError as e:
                last_exc = e
                log.warning("RSC %s loi (lan %d/%d): %s",
                            action_id, attempt, self.cfg.max_retry, e)
                time.sleep(self.cfg.retry_backoff * attempt)
        raise RuntimeError(f"RSC {action_id} that bai") from last_exc

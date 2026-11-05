"""Polite, cached EDGAR HTTP client. Instructor-only.

- User-Agent comes from SEC_USER_AGENT (required, never hardcoded).
- <= 8 requests/second (SEC fair access allows 10).
- Retries with exponential backoff on 429/5xx/network errors.
- Every raw response is cached (gzip) under data/raw, so reruns don't refetch.
"""

from __future__ import annotations

import gzip
import json
import os
import random
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

MAX_RPS = 8
CACHE_ROOT = Path(os.environ.get("EDGAR_CACHE", "data/raw"))


def _user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        sys.exit(
            "SEC_USER_AGENT is not set. The SEC requires a User-Agent that identifies you, "
            'e.g. export SEC_USER_AGENT="Your Name your.email@example.edu"'
        )
    return ua


class EdgarClient:
    def __init__(self) -> None:
        self._client: httpx.Client | None = None  # created on first network request
        self._lock = threading.Lock()
        self._last = 0.0
        self.network_requests = 0
        self.cache_hits = 0

    def _cache_path(self, url: str) -> Path:
        u = urlparse(url)
        return CACHE_ROOT / u.netloc / (u.path.lstrip("/") + ".gz")

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last + 1.0 / MAX_RPS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def get_bytes(self, url: str) -> bytes:
        path = self._cache_path(url)
        if path.exists():
            self.cache_hits += 1
            return gzip.decompress(path.read_bytes())
        if self._client is None:  # cache miss: only now do we need the User-Agent
            self._client = httpx.Client(
                headers={"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"},
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
            )
        delay = 1.0
        for attempt in range(7):
            self._throttle()
            try:
                r = self._client.get(url)
                self.network_requests += 1
                if r.status_code == 200:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(".tmp")
                    tmp.write_bytes(gzip.compress(r.content))
                    tmp.replace(path)
                    return r.content
                if r.status_code == 404:
                    raise FileNotFoundError(url)
                if r.status_code not in (403, 429, 500, 502, 503, 504):
                    r.raise_for_status()
                # 403 from SEC usually means "slow down" (or a bad User-Agent).
                print(f"  HTTP {r.status_code} on {url}; retry {attempt + 1}", file=sys.stderr)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                print(f"  {type(e).__name__} on {url}; retry {attempt + 1}", file=sys.stderr)
            time.sleep(delay + random.random())
            delay = min(delay * 2, 60)
        raise RuntimeError(f"giving up on {url}")

    def get_json(self, url: str):
        return json.loads(self.get_bytes(url))

"""BaseClient — shared HTTP plumbing for every source.

Three concerns, deliberately kept here so each source client stays a thin map of
endpoints:
  * Rate limiting   — token-bucket per API (CoinGecko 30/min free, GitHub
                      5000/hr authed, etc.)
  * Caching         — on-disk JSON keyed by url+params; respects TTL. Critical
                      for CoinGecko credit budgets and for fast local iteration.
  * Retry/backoff   — exponential backoff on 429 + 5xx.

Synchronous (httpx.Client) on purpose: it keeps vcrpy cassettes and tests
straightforward for a single-founder MVP. Swap to httpx.AsyncClient later if a
refresh fan-out needs the concurrency.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from dyor.config import PROJECT_ROOT, load_config


class RateLimiter:
    """Token bucket. `acquire()` blocks until a token is available."""

    def __init__(self, rate_per_min: float, burst: float | None = None) -> None:
        self.rate_per_sec = rate_per_min / 60.0
        self.capacity = burst if burst is not None else max(1.0, rate_per_min / 6.0)
        self._tokens = self.capacity
        self._last = time.monotonic()

    def acquire(self) -> None:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate_per_sec)
        self._last = now
        if self._tokens < 1.0:
            wait = (1.0 - self._tokens) / self.rate_per_sec
            time.sleep(wait)
            self._tokens = 0.0
            self._last = time.monotonic()
        else:
            self._tokens -= 1.0


class FileCache:
    """Trivial on-disk JSON cache keyed by a hash of (url, params)."""

    def __init__(self, cache_dir: Path, ttl_seconds: int | None) -> None:
        self.dir = cache_dir
        self.ttl = ttl_seconds  # None disables expiry; 0 = always stale
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(url: str, params: dict | None) -> str:
        blob = url + "?" + json.dumps(params or {}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def get(self, url: str, params: dict | None) -> Any | None:
        path = self.dir / f"{self._key(url, params)}.json"
        if not path.exists():
            return None
        if self.ttl is not None and (time.time() - path.stat().st_mtime) > self.ttl:
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, url: str, params: dict | None, value: Any) -> None:
        path = self.dir / f"{self._key(url, params)}.json"
        path.write_text(json.dumps(value))


class BaseClient:
    """Base for all source clients. Subclasses set `name` and call `get_json`."""

    name: str = "base"
    default_rate_per_min: float = 60.0

    def __init__(
        self,
        config: dict | None = None,
        *,
        use_cache: bool = True,
        rate_per_min: float | None = None,
    ) -> None:
        self.config = config if config is not None else load_config()
        ingestion = self.config["ingestion"]
        self.retry_cfg = ingestion["retry"]
        self.use_cache = use_cache

        rpm = rate_per_min or self._rate_from_config() or self.default_rate_per_min
        self.limiter = RateLimiter(rpm)

        cache_dir = PROJECT_ROOT / ingestion["cache_dir"] / self.name
        self.cache = FileCache(cache_dir, ingestion["cache_ttl_seconds"])
        self._client = httpx.Client(timeout=30.0, headers=self.default_headers())

    # -- hooks for subclasses ------------------------------------------------
    def _rate_from_config(self) -> float | None:
        src = self.config["ingestion"]["sources"].get(self.name, {})
        return src.get("rate_limit_per_min")

    def default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "dyor/0.1"}

    # -- core request --------------------------------------------------------
    def get_json(self, url: str, params: dict | None = None) -> Any:
        """GET with cache → rate-limit → request → retry/backoff."""
        if self.use_cache:
            cached = self.cache.get(url, params)
            if cached is not None:
                return cached

        data = self._request_with_retry(url, params)

        if self.use_cache:
            self.cache.set(url, params, data)
        return data

    def _request_with_retry(self, url: str, params: dict | None) -> Any:
        max_attempts = self.retry_cfg["max_attempts"]
        base = self.retry_cfg["backoff_base_seconds"]
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            self.limiter.acquire()
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    resp.raise_for_status()
                resp.raise_for_status()
                # An empty 200 body is "no data", not a parse error to retry —
                # e.g. DefiLlama /tvl/{slug} for a protocol with no TVL value.
                if not resp.content or not resp.text.strip():
                    return None
                return resp.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status != 429 and status < 500:
                    raise  # client error (404, 401, ...) — don't retry
                # Honor Retry-After on 429 (capped); else exponential backoff.
                wait = base * (2**attempt)
                if status == 429:
                    retry_after = exc.response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        wait = min(float(retry_after), 65.0)
                time.sleep(wait)
            except (httpx.TransportError, json.JSONDecodeError) as exc:
                last_exc = exc
                time.sleep(base * (2**attempt))

        raise RuntimeError(
            f"{self.name}: GET {url} failed after {max_attempts} attempts"
        ) from last_exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BaseClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

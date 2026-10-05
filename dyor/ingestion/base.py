"""BaseClient — shared HTTP plumbing for every source.

Three concerns, deliberately kept here so each source client stays a thin map of
endpoints:
  * Rate limiting   — token-bucket per API, SHARED across every client instance
                      in the process (the API serves many requests at once; one
                      bucket per instance let the aggregate blow past a per-IP
                      upstream limit and sleep inside worker threads on 429s).
  * Caching         — on-disk JSON keyed by url+params; respects TTL; atomic
                      writes; expired entries evicted once per process.
  * Retry/backoff   — exponential backoff on 429 + 5xx.

Synchronous (httpx.Client) on purpose: it keeps vcrpy cassettes and tests
straightforward for a single-founder MVP. Swap to httpx.AsyncClient later if a
refresh fan-out needs the concurrency.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from dyor.config import PROJECT_ROOT, load_config, redact_secrets

# Sentinel stored for an empty-200 response so "the upstream had nothing" is a
# cache HIT, not a miss that refetches every run (DefiLlama /tvl for no-TVL
# protocols used to be re-requested on every collect).
_EMPTY = {"__dyor_empty__": True}


class RateLimiter:
    """Token bucket. `acquire()` blocks until a token is available. Thread-safe."""

    def __init__(self, rate_per_min: float, burst: float | None = None) -> None:
        self.rate_per_min = rate_per_min
        self.rate_per_sec = rate_per_min / 60.0
        self.capacity = burst if burst is not None else max(1.0, rate_per_min / 6.0)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        # Held across the sleep on purpose: callers are queued one at a time,
        # which is exactly the pacing the upstream limit demands.
        with self._lock:
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


_SHARED_LIMITERS: dict[tuple[str, float], RateLimiter] = {}
_SHARED_LOCK = threading.Lock()


def shared_limiter(name: str, rate_per_min: float) -> RateLimiter:
    """One bucket per (source, rate) for the whole process."""
    key = (name, float(rate_per_min))
    with _SHARED_LOCK:
        lim = _SHARED_LIMITERS.get(key)
        if lim is None:
            lim = _SHARED_LIMITERS[key] = RateLimiter(rate_per_min)
        return lim


class FileCache:
    """On-disk JSON cache keyed by a hash of (url, params). Writes are atomic."""

    def __init__(self, cache_dir: Path, ttl_seconds: int | None) -> None:
        self.dir = cache_dir
        self.ttl = ttl_seconds  # None disables expiry; 0 = always stale
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(url: str, params: dict | None) -> str:
        blob = url + "?" + json.dumps(params or {}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _expired(self, path: Path) -> bool:
        return self.ttl is not None and (time.time() - path.stat().st_mtime) > self.ttl

    def get(self, url: str, params: dict | None) -> Any | None:
        path = self.dir / f"{self._key(url, params)}.json"
        if not path.exists() or self._expired(path):
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, url: str, params: dict | None, value: Any) -> None:
        # tmp + rename so a concurrent reader never sees a half-written file.
        path = self.dir / f"{self._key(url, params)}.json"
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(value))
        os.replace(tmp, path)

    def evict_expired(self) -> int:
        """Delete expired entries (and stray temp files). Returns the count."""
        if self.ttl is None:
            return 0
        removed = 0
        for p in self.dir.iterdir():
            try:
                if p.suffix == ".tmp" or (p.suffix == ".json" and self._expired(p)):
                    p.unlink()
                    removed += 1
            except OSError:
                continue
        return removed


_EVICTED_DIRS: set[Path] = set()


def _evict_once(cache: FileCache) -> None:
    """Evict expired entries the first time a cache dir is opened in this process
    — cheap (one directory scan) and keeps the on-disk cache from growing forever."""
    with _SHARED_LOCK:
        if cache.dir in _EVICTED_DIRS:
            return
        _EVICTED_DIRS.add(cache.dir)
    with contextlib.suppress(OSError):
        cache.evict_expired()


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
        self.limiter = shared_limiter(self.name, rpm)

        cache_dir = PROJECT_ROOT / ingestion["cache_dir"] / self.name
        self.cache = FileCache(cache_dir, ingestion["cache_ttl_seconds"])
        if use_cache:
            _evict_once(self.cache)
        self._client = httpx.Client(timeout=30.0, headers=self.default_headers())

    # -- hooks for subclasses ------------------------------------------------
    def _rate_from_config(self) -> float | None:
        src = self.config["ingestion"]["sources"].get(self.name, {})
        return src.get("rate_limit_per_min")

    #: 4xx statuses worth retrying with backoff (rate limiting). Subclasses extend it.
    retry_statuses: frozenset[int] = frozenset({429})

    def default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "User-Agent": "dyor/0.1 (+https://dyor.cryptoopsec.com)"}

    # -- core request --------------------------------------------------------
    def get_json(self, url: str, params: dict | None = None) -> Any:
        """GET with cache → rate-limit → request → retry/backoff."""
        if self.use_cache:
            cached = self.cache.get(url, params)
            if cached is not None:
                return None if cached == _EMPTY else cached

        data = self._request_with_retry(url, params)

        if self.use_cache:
            self.cache.set(url, params, _EMPTY if data is None else data)
        return data

    def _request_with_retry(self, url: str, params: dict | None) -> Any:
        max_attempts = self.retry_cfg["max_attempts"]
        base = self.retry_cfg["backoff_base_seconds"]
        last_exc: Exception | None = None

        for attempt in range(max_attempts):
            self.limiter.acquire()
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                # An empty 200 body is "no data", not a parse error to retry —
                # e.g. DefiLlama /tvl/{slug} for a protocol with no TVL value.
                if not resp.content or not resp.text.strip():
                    return None
                return resp.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                if status not in self.retry_statuses and status < 500:
                    raise  # client error (404, 401 ...): do not retry
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

        # Keys can live in a URL path (DefiLlama Pro) — never let one into a log.
        raise RuntimeError(
            f"{self.name}: GET {redact_secrets(url)} failed after {max_attempts} attempts"
        ) from last_exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

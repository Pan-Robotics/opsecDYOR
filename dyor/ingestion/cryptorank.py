"""CryptoRank client — unlock / vesting overhang.

Two access paths:

* **v0 (open, no key)** — the undocumented endpoint CryptoRank's own frontend
  used. It carried `hasVesting` plus supply figures, which gave us an
  unlock-overhang signal without a paid key. **In September 2026 it went behind a
  Cloudflare challenge** (HTTP 403 `text/html` for any non-browser client;
  spoofed browser headers don't get through). It is therefore **disabled by
  default** in `config.yaml`.

* **v3 (documented, keyed)** — `X-Api-Key` from `DYOR_CRYPTORANK_API_KEY`.
  Verified live 2026-09-26:
    - `GET /v3/currencies/map`            → {data: [{id, slug, symbol, name}]}
    - `GET /v3/currencies/{id}`           → CurrencyProfileDto with
                                             circulatingSupply / totalSupply / maxSupply
    - `GET /v3/currencies/{id}/vesting/allocations`  (**Pro plan**) → [{lockedTokens,
                                             totalTokens, lockedPercent, ...}]
    - `GET /v3/currencies/{id}/vesting/events?filter=upcoming` (**Pro**) →
                                             [{time, unlockTokens, unlockValue, ...}]
    - `GET /v3/status` (free)             → {plan, rateLimitPerMinute, credits, endpoints}

  The overhang signal NEEDS the vesting endpoints: supply alone cannot tell a
  vesting lock from structurally-uncreated supply (un-mined BTC), which is the
  exact conflation the feature exists to avoid. So `enabled` is True only when
  the key's plan exposes `/vesting/allocations`; on a plan without it (e.g.
  "Sandbox") the feed reports `off` and spends no credits. Upgrading the plan
  lights the feed up with no code change.
"""

from __future__ import annotations

from typing import Any

from dyor.config import get_settings
from dyor.ingestion.base import BaseClient

V0_BASE = "https://api.cryptorank.io/v0"
V3_BASE = "https://api.cryptorank.io/v3"
_VESTING_ENDPOINT = "/v3/currencies/{id}/vesting/allocations"


class CryptoRankClient(BaseClient):
    name = "cryptorank"
    default_rate_per_min = 60.0

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        self._api_key = get_settings().cryptorank_api_key
        super().__init__(config, **kwargs)
        src = self.config["ingestion"]["sources"].get("cryptorank", {})
        self._v0_enabled = bool(src.get("enabled", True))
        self._id_map: dict[str, int] | None = None
        self._status: dict[str, Any] | None = None

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        key = get_settings().cryptorank_api_key
        if key:
            headers["X-Api-Key"] = key
        return headers

    # -- plan / capability -----------------------------------------------------
    def status(self) -> dict[str, Any]:
        """`/v3/status` — plan, credits and the endpoints this key may call.
        Free (no credit), cached like any GET. Empty dict without a key."""
        if not self._api_key:
            return {}
        if self._status is None:
            try:
                payload = self.get_json(f"{V3_BASE}/status")
                self._status = payload.get("data", payload) if isinstance(payload, dict) else {}
            except Exception:
                self._status = {}
        return self._status

    @property
    def plan(self) -> str | None:
        return self.status().get("plan")

    @property
    def vesting_available(self) -> bool:
        return _VESTING_ENDPOINT in (self.status().get("endpoints") or [])

    @property
    def enabled(self) -> bool:
        """Can this client produce the unlock-overhang signal?

        Keyed: only if the plan exposes the vesting endpoints. Keyless: only if
        the (dead) v0 path is explicitly enabled in config. Otherwise the
        collector reports the feed `off` and makes no request.
        """
        if self._api_key:
            return self.vesting_available
        return self._v0_enabled

    @property
    def disabled_reason(self) -> str | None:
        """Human-readable reason `enabled` is False, for the CLI to surface once."""
        if self.enabled:
            return None
        if self._api_key:
            return (f"CryptoRank key present but plan '{self.plan or '?'}' has no vesting "
                    f"endpoints — unlock_overhang is off (needs the Pro plan)")
        return "CryptoRank v0 is disabled in config (open endpoint is dead); set DYOR_CRYPTORANK_API_KEY"

    # -- public ----------------------------------------------------------------
    def coin(self, key: str) -> dict[str, Any]:
        """Supply + vesting facts for a CryptoRank slug (e.g. 'aave'), in the
        v0 field names the collector consumes:
          availableSupply, maxSupply, hasVesting, fundIds, crowdsales,
          and (v3 Pro only) nextUnlockUsd.
        Raises LookupError (→ not-found → feed `empty`) for an unknown slug."""
        if self._api_key:
            return self._coin_v3(key)
        return self._coin_v0(key)

    # -- v0 (open; dead as of 2026-09) -----------------------------------------
    def _coin_v0(self, key: str) -> dict[str, Any]:
        payload = self.get_json(f"{V0_BASE}/coins/{key}")
        return payload.get("data", payload) if isinstance(payload, dict) else {}

    # -- v3 (keyed) --------------------------------------------------------------
    def _load_id_map(self) -> dict[str, int]:
        if self._id_map is None:
            payload = self.get_json(f"{V3_BASE}/currencies/map")
            rows = payload.get("data", payload) if isinstance(payload, dict) else payload
            self._id_map = {str(r["slug"]).lower(): r["id"]
                            for r in (rows or []) if isinstance(r, dict) and r.get("slug")}
        return self._id_map

    def _coin_v3(self, key: str) -> dict[str, Any]:
        cid = self._load_id_map().get(key.lower())
        if cid is None:
            raise LookupError(f"cryptorank: '{key}' not found in currency map")
        payload = self.get_json(f"{V3_BASE}/currencies/{cid}")
        prof = payload.get("data", payload) if isinstance(payload, dict) else {}

        out: dict[str, Any] = {
            "availableSupply": prof.get("circulatingSupply"),
            "maxSupply": prof.get("maxSupply") or prof.get("totalSupply"),
            "hasVesting": None,          # unknown until the vesting endpoint says
            "fundIds": [],               # not in the v3 profile
            "crowdsales": [],
            "nextUnlockUsd": None,
        }
        if not self.vesting_available:
            return out

        allocs = self.get_json(f"{V3_BASE}/currencies/{cid}/vesting/allocations")
        allocs = allocs.get("data", allocs) if isinstance(allocs, dict) else allocs
        out["hasVesting"] = bool(allocs)
        if allocs:
            locked = sum(float(a.get("lockedTokens") or 0) for a in allocs)
            total = sum(float(a.get("totalTokens") or 0) for a in allocs)
            if total > 0:
                out["lockedFraction"] = locked / total
            events = self.get_json(f"{V3_BASE}/currencies/{cid}/vesting/events",
                                   params={"filter": "upcoming", "sortBy": "time"})
            events = events.get("data", events) if isinstance(events, dict) else events
            if events:
                out["nextUnlockUsd"] = events[0].get("unlockValue")
        return out

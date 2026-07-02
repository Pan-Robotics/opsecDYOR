"""CryptoRank client — unlock / vesting overhang.

CryptoRank's documented v1/v2 REST API requires a key (401 without one). But its
**v0** API — the undocumented endpoint its own frontend uses — is open and needs
no key. We use `v0/coins/{key}`, which carries `hasVesting` plus supply figures
(`availableSupply`, `maxSupply`, `percentOfCircSupply`).

That lets us derive an unlock-overhang signal WITHOUT a paid key: the fraction of
max supply still locked, counted only when the token is actually on a vesting
schedule (so structurally-uncreated supply like un-mined BTC isn't mistaken for a
pending dump). The precise per-event next-unlock amount still needs the keyed
v1 `currencies/token-unlock` endpoint — a Stage-2 enhancement.
"""

from __future__ import annotations

from typing import Any

from dyor.ingestion.base import BaseClient

V0_BASE = "https://api.cryptorank.io/v0"


class CryptoRankClient(BaseClient):
    name = "cryptorank"
    default_rate_per_min = 60.0

    def coin(self, key: str) -> dict[str, Any]:
        """Open v0 coin detail (no key). `key` is CryptoRank's slug, e.g. 'aave'."""
        payload = self.get_json(f"{V0_BASE}/coins/{key}")
        return payload.get("data", payload)

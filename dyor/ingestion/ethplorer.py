"""Ethplorer client — holder concentration for Ethereum ERC-20 tokens (free).

Ethplorer exposes a public demo key `freekey` that covers `getTopTokenHolders`
and `getTokenInfo` — a genuinely free way to read holder distribution without an
Etherscan Pro key. Ethereum-mainnet only, so it covers ETH-native governance
tokens (AAVE, UNI, LDO, CRV); L2/own-chain tokens (GMX on Arbitrum, HYPE) are
out of scope and surface as None upstream.

A real key can be supplied via config; otherwise `freekey` is used (lower rate
limits, but fine for a small screener).
"""

from __future__ import annotations

from typing import Any

from dyor.ingestion.base import BaseClient

BASE = "https://api.ethplorer.io"


class EthplorerClient(BaseClient):
    name = "ethplorer"
    default_rate_per_min = 30.0  # freekey is rate-limited; be gentle

    def __init__(self, config: dict | None = None, *, api_key: str = "freekey", **kwargs) -> None:
        super().__init__(config, **kwargs)
        self._api_key = api_key

    def top_token_holders(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        """Top holders of an ERC-20: [{address, balance, share}, ...].

        `share` is each holder's percentage of total supply.
        """
        payload = self.get_json(
            f"{BASE}/getTopTokenHolders/{address.lower()}",
            params={"apiKey": self._api_key, "limit": limit},
        )
        return payload.get("holders", [])

"""Sourcify client — open, keyless contract source-verification.

`v2/contract/{chainId}/{address}` returns a match (exact/partial) for verified
contracts and 404 for anything Sourcify doesn't have. We use it as a SAFE,
positive signal: a confirmed match → `contract_verified = True`. We never infer
`False` from a 404, because absence from Sourcify ≠ unverified on-chain (the
contract may be verified on Etherscan but not mirrored here). Inferring False
could wrongly *zero* a legitimate token's score, so we return None when unknown.

A definitive "unverified" signal (to actually trip the gate) needs an
authoritative source like Etherscan `getsourcecode` — a keyed Stage-2 add.
"""

from __future__ import annotations

import httpx

from dyor.ingestion.base import BaseClient

BASE = "https://sourcify.dev/server"


class SourcifyClient(BaseClient):
    name = "sourcify"
    default_rate_per_min = 30.0

    def is_verified(self, address: str, chain_id: int = 1) -> bool | None:
        """True if Sourcify has a source match; None if unknown (not 'False').

        Returns None on a 404 (not in Sourcify) or any transport hiccup — the
        caller treats None as "no positive signal", never as a disqualifier.
        """
        try:
            data = self.get_json(f"{BASE}/v2/contract/{chain_id}/{address.lower()}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        match = data.get("match") or data.get("runtimeMatch")
        return True if match and match != "no_match" else None

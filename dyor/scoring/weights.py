"""Domain weights for the composite score.

Weights are grouped by domain (fundamental, tokenomics, on-chain, social, dev)
and must sum to 1.0. Loaded from `config.yaml` but validated here so a bad edit
fails loudly instead of silently skewing every score.
"""

from __future__ import annotations

from dataclasses import dataclass

from dyor.config import load_config

_SUM_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Weights:
    """Validated domain weights."""

    by_domain: dict[str, float]

    def __post_init__(self) -> None:
        if not self.by_domain:
            raise ValueError("weights are empty")
        total = sum(self.by_domain.values())
        if abs(total - 1.0) > _SUM_TOLERANCE:
            raise ValueError(f"weights must sum to 1.0, got {total:.6f}")
        for domain, w in self.by_domain.items():
            if w < 0:
                raise ValueError(f"weight for '{domain}' is negative: {w}")

    def get(self, domain: str) -> float:
        return self.by_domain[domain]

    @property
    def domains(self) -> list[str]:
        return list(self.by_domain)


def load_weights(config: dict | None = None) -> Weights:
    cfg = config if config is not None else load_config()
    return Weights(by_domain=dict(cfg["scoring"]["weights"]))

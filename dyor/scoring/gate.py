"""Hard disqualifier gating — gate, don't average.

A fatal flaw (unverified contract, anonymous team, no audit, extreme dilution
overhang, or dead-token criteria) must not be offset by a strong factor
elsewhere. Each triggered rule either zeroes the score or caps it at a ceiling;
when several fire, the strictest (lowest) outcome wins.

Each rule is a pure predicate over a token's metric record (a plain dict). A
rule returns True when the flag is *tripped*. Missing data does NOT trip a rule
(we don't punish absence here — surface it upstream instead).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dyor.config import load_config


@dataclass(frozen=True)
class GateResult:
    """Outcome of applying all disqualifier rules to one token."""

    flags: list[str] = field(default_factory=list)
    cap: float | None = None  # ceiling in [0, 1]; None = no cap

    @property
    def zeroed(self) -> bool:
        return self.cap == 0.0

    def apply(self, raw_score: float) -> float:
        """Clamp a raw [0, 1] score to the gate's ceiling."""
        if self.cap is None:
            return raw_score
        return min(raw_score, self.cap)


# --- Rule predicates -------------------------------------------------------
# Each takes (record, rule_cfg, gating_cfg) and returns True if the flag trips.

def _unverified_contract(rec: dict, _rule: dict, _cfg: dict) -> bool:
    return rec.get("contract_verified") is False


def _anonymous_team(rec: dict, _rule: dict, _cfg: dict) -> bool:
    return rec.get("team_anonymous") is True


def _no_audit(rec: dict, _rule: dict, _cfg: dict) -> bool:
    return rec.get("audited") is False


def _extreme_fdv_mcap(rec: dict, rule: dict, _cfg: dict) -> bool:
    ratio = rec.get("fdv_mcap_ratio")
    if ratio is None:
        return False
    return ratio > rule.get("threshold", 10.0)


def _dead_token(rec: dict, _rule: dict, cfg: dict) -> bool:
    """Any one criterion trips it: stale repo or no volume.

    Price drawdown from ATH is deliberately NOT a criterion — a deep drawdown
    alone reflects price action, not project death, and must not zero a token.
    """
    crit = cfg.get("dead_token", {})
    days = rec.get("days_since_last_commit")
    if days is not None and days >= crit.get("no_commits_days", 180):
        return True
    vol = rec.get("daily_volume_usd")
    if vol is not None and vol < crit.get("min_daily_volume_usd", 1000.0):
        return True
    return False


RULES = {
    "unverified_contract": _unverified_contract,
    "anonymous_team": _anonymous_team,
    "no_audit": _no_audit,
    "extreme_fdv_mcap": _extreme_fdv_mcap,
    "dead_token": _dead_token,
}


def evaluate(record: dict, config: dict | None = None) -> GateResult:
    """Run every configured rule over `record` and combine the outcomes.

    `action: zero` sets cap = 0.0; `action: cap` sets cap = its `cap` value.
    The strictest (lowest) cap across all tripped rules wins.
    """
    cfg = config if config is not None else load_config()
    gating = cfg["gating"]
    rules_cfg = gating["rules"]

    flags: list[str] = []
    cap: float | None = None

    for name, rule_cfg in rules_cfg.items():
        predicate = RULES.get(name)
        if predicate is None:  # config references an unimplemented rule
            continue
        if predicate(record, rule_cfg, gating):
            flags.append(name)
            this_cap = 0.0 if rule_cfg.get("action") == "zero" else rule_cfg.get("cap", 1.0)
            cap = this_cap if cap is None else min(cap, this_cap)

    return GateResult(flags=flags, cap=cap)

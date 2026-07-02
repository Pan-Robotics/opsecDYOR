"""Alerting — turn run-over-run changes and live thresholds into notifications.

Pure detectors (data in → list[Alert] out) so they unit-test offline, plus
sinks (console always; webhook if DYOR_ALERT_WEBHOOK is set). Wired into
`dyor refresh`, which compares the new collection run against the previous one.

Detectors:
  * score_change   — a token's final score jumped up/down past a threshold
  * tier_change    — a token crossed a tier boundary (A↔B↔C↔D)
  * new_flag       — a gate flag appeared that wasn't there last run (critical)
  * unlock_cliff   — a token's unlock overhang is above a threshold
  * narrative      — a sector's 24h momentum is above a threshold
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from dyor.config import get_settings

_TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}  # lower = better


@dataclass(frozen=True)
class Alert:
    kind: str
    subject: str
    message: str
    severity: str  # "info" | "warn" | "critical"


def _tier_letter(tier: str) -> str:
    return tier.strip()[:1] if tier else "?"


def _index(results: Iterable[Any]) -> dict[str, Any]:
    """token -> result, accepting ScoreResult objects or plain dicts."""
    out = {}
    for r in results:
        token = r["token"] if isinstance(r, dict) else r.token
        out[token] = r
    return out


def _get(r: Any, attr: str):
    return r.get(attr) if isinstance(r, dict) else getattr(r, attr)


# --- detectors -------------------------------------------------------------

def score_change_alerts(prev, curr, *, drop: float = 0.10, rise: float = 0.15) -> list[Alert]:
    pi, ci = _index(prev), _index(curr)
    out: list[Alert] = []
    for token, c in ci.items():
        if token not in pi:
            continue
        delta = _get(c, "final_score") - _get(pi[token], "final_score")
        if delta <= -drop:
            out.append(Alert("score_drop", token,
                             f"score fell {delta:+.2f} to {_get(c, 'final_score'):.2f}", "warn"))
        elif delta >= rise:
            out.append(Alert("score_rise", token,
                             f"score rose {delta:+.2f} to {_get(c, 'final_score'):.2f}", "info"))
    return out


def tier_change_alerts(prev, curr) -> list[Alert]:
    pi, ci = _index(prev), _index(curr)
    out: list[Alert] = []
    for token, c in ci.items():
        if token not in pi:
            continue
        old, new = _tier_letter(_get(pi[token], "tier")), _tier_letter(_get(c, "tier"))
        if old != new:
            worse = _TIER_ORDER.get(new, 9) > _TIER_ORDER.get(old, 9)
            out.append(Alert("tier_change", token, f"tier {old} → {new}",
                             "warn" if worse else "info"))
    return out


def new_flag_alerts(prev, curr) -> list[Alert]:
    pi, ci = _index(prev), _index(curr)
    out: list[Alert] = []
    for token, c in ci.items():
        old_flags = set(_get(pi[token], "flags")) if token in pi else set()
        for flag in _get(c, "flags"):
            if flag not in old_flags:
                out.append(Alert("new_flag", token, f"new gate flag: {flag}", "critical"))
    return out


def unlock_alerts(records: Iterable[dict], threshold: float = 0.5) -> list[Alert]:
    out: list[Alert] = []
    for rec in records:
        oh = rec.get("unlock_overhang")
        if oh is not None and oh >= threshold:
            out.append(Alert("unlock_cliff", rec.get("token", "?"),
                             f"unlock overhang {oh:.0%} of max supply still locked", "warn"))
    return out


def narrative_alerts(categories: Iterable[dict], threshold: float = 10.0) -> list[Alert]:
    out: list[Alert] = []
    for cat in categories:
        chg = cat.get("change_24h")
        if chg is not None and chg >= threshold:
            out.append(Alert("narrative", cat.get("name", "?"),
                             f"sector +{chg:.1f}% (24h)", "info"))
    return out


def evaluate(
    prev, curr, *,
    records: Iterable[dict] | None = None,
    narratives: Iterable[dict] | None = None,
    drop: float = 0.10, rise: float = 0.15,
    unlock_threshold: float = 0.5, narrative_threshold: float = 10.0,
) -> list[Alert]:
    """Run all applicable detectors and return the combined, severity-sorted list."""
    alerts: list[Alert] = []
    alerts += new_flag_alerts(prev, curr)
    alerts += tier_change_alerts(prev, curr)
    alerts += score_change_alerts(prev, curr, drop=drop, rise=rise)
    if records is not None:
        alerts += unlock_alerts(records, unlock_threshold)
    if narratives is not None:
        alerts += narrative_alerts(narratives, narrative_threshold)
    order = {"critical": 0, "warn": 1, "info": 2}
    return sorted(alerts, key=lambda a: order.get(a.severity, 9))


# --- sinks -----------------------------------------------------------------

_ICON = {"critical": "🔴", "warn": "🟠", "info": "🔵"}


def format_alerts(alerts: list[Alert]) -> str:
    if not alerts:
        return "no alerts"
    return "\n".join(f"{_ICON.get(a.severity, '•')} [{a.kind}] {a.subject}: {a.message}"
                     for a in alerts)


def console_sink(alerts: list[Alert]) -> None:
    print(format_alerts(alerts))


def webhook_sink(alerts: list[Alert], url: str) -> None:
    """POST alerts to a webhook (Slack/Discord-compatible `text` payload)."""
    import httpx

    httpx.post(url, json={"text": format_alerts(alerts)}, timeout=15)


def emit(alerts: list[Alert]) -> None:
    """Console always; webhook too if DYOR_ALERT_WEBHOOK is configured."""
    console_sink(alerts)
    url = get_settings().alert_webhook
    if url and alerts:
        try:
            webhook_sink(alerts, url)
        except Exception as exc:  # noqa: BLE001 — a down webhook must not crash a run
            print(f"(alert webhook failed: {type(exc).__name__})")

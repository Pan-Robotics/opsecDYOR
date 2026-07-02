"""Analyst memo — turn a structured analysis into a reasoned narrative.

A tier is not research. This composes a defensible write-up from the data: the
verdict, what drove it, the risks, the framework's "break your thesis" questions
answered with the actual numbers, and an honest confidence caveat. Deterministic
(no LLM needed) so it's reproducible and testable; an agent can also use it as the
factual skeleton for a richer narrative.
"""

from __future__ import annotations

from dyor.api.serialize import analyze_to_dict


def _pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def _top_domains(domain_scores: dict, n: int = 2, best: bool = True):
    items = [(d, v) for d, v in domain_scores.items() if v is not None]
    items.sort(key=lambda kv: kv[1], reverse=best)
    return items[:n]


def memo_from_analysis(d: dict) -> str:
    """Build the memo text from an analyze dict (api.serialize.analyze_to_dict)."""
    r, s, rec = d.get("resolved"), d.get("score"), d.get("record", {})
    if r is None:
        return f"Could not resolve '{d.get('query')}' to a token."
    if s is None:
        return f"{r['name']} ({r['symbol']}) resolved but had no market data to score."

    cls = rec.get("class", {})
    feats = rec.get("features", {})
    m = rec.get("market") or {}
    lines: list[str] = []

    # Verdict
    lines.append(f"# {r['name']} ({r['symbol']}) — {s['tier']}  ·  score {s['final_score']}")
    lines.append(f"**Asset class:** {cls.get('label')} · **confidence:** {s.get('confidence')} "
                 f"(coverage {_pct(s.get('coverage'))}, tier-stability {_pct(s.get('tier_stability'))})"
                 + (f" · ranked #{d['rank']} of {d['peer_count'] + 1} peers" if d.get('rank') else ""))
    lines.append(f"_{cls.get('description','')}_")

    # What drove it
    strong = _top_domains(s["domain_scores"], best=True)
    weak = _top_domains(s["domain_scores"], best=False)
    lines.append("\n## What drove the score")
    if strong:
        lines.append("Strongest: " + ", ".join(f"**{d}** ({v:.2f})" for d, v in strong) + ".")
    if weak:
        lines.append("Weakest: " + ", ".join(f"**{d}** ({v:.2f})" for d, v in weak) + ".")

    # Risks
    lines.append("\n## Risks")
    if s["flags"]:
        lines.append(f"- 🔴 **Gate flags:** {', '.join(s['flags'])} — these capped or zeroed the score.")
    for a in s.get("advisories", []):
        lines.append(f"- ⚠ {a}")
    oh = feats.get("unlock_overhang")
    if oh is not None and oh >= 0.3:
        lines.append(f"- ⚠ **Unlock overhang:** ~{oh:.0%} of max supply still vesting — supply risk.")
    conc = feats.get("top10_concentration")
    if conc is not None and conc >= 0.5:
        lines.append(f"- ⚠ **Concentration:** top-10 wallets hold ~{conc:.0%} of supply.")
    if (s.get("coverage") or 1) < 0.5:
        lines.append(f"- ⚠ **Thin data** ({_pct(s.get('coverage'))} coverage) — treat the tier as low-confidence.")
    miss = [k for k in ("cryptorank", "santiment", "defillama")
            if (rec.get("feeds") or {}).get(k) in ("error", "empty")]
    if miss:
        lines.append(f"- ℹ Missing/empty feeds: {', '.join(miss)} (some signals not captured).")
    if len(lines) and not lines[-1].startswith("-"):
        lines.append("- No hard red flags surfaced.")

    # Break your thesis (answered with data)
    lines.append("\n## Break your thesis")
    ag = feats.get("address_growth")
    lines.append(f"- **Retention / usage:** active-address growth "
                 + (f"{ag:+.0%}." if ag is not None else "not available."))
    lines.append("- **Supply shock:** "
                 + (f"~{oh:.0%} of supply still unlocking — watch the schedule." if oh else
                    "no major vesting overhang detected (or not tracked)."))
    fdv = feats.get("fdv_mcap_ratio")
    lines.append("- **Dilution:** "
                 + (f"FDV/MCAP {fdv:.2f}× ({'high overhang' if fdv > 2 else 'modest'})." if fdv else "n/a."))
    dd = m.get("ath_change_pct")
    lines.append("- **Bear-market survival:** "
                 + (f"{dd:.0f}% from ATH." if dd is not None else "n/a.")
                 + " Alts fall harder than BTC — size accordingly.")
    va = feats.get("value_accrual")
    if va is not None:
        lines.append(f"- **Value accrual:** ~{va:.0%} of revenue routed to holders (token sink).")

    # Caveat
    lines.append(f"\n_Peer set: {d.get('peer_count', 0)} tokens. Research aid — not financial advice._")
    return "\n".join(lines)


def analyst_memo(query: str, config: dict | None = None, *, peer_mode: str = "class") -> str:
    """Resolve → analyze → memo, in one call."""
    from dyor.analyze import analyze_token

    res = analyze_token(query, config, peer_mode=peer_mode)
    return memo_from_analysis(analyze_to_dict(res))

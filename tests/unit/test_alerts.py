from dyor import alerts


def _r(token, score, tier, flags=()):
    return {"token": token, "final_score": score, "tier": tier, "flags": list(flags)}


def test_score_change_drop_and_rise():
    prev = [_r("a", 0.70, "B — qualified"), _r("b", 0.40, "C — watchlist")]
    curr = [_r("a", 0.55, "C — watchlist"), _r("b", 0.60, "B — qualified")]
    found = {al.kind: al for al in alerts.score_change_alerts(prev, curr, drop=0.1, rise=0.15)}
    assert "score_drop" in found and found["score_drop"].subject == "a"
    assert "score_rise" in found and found["score_rise"].subject == "b"


def test_tier_change_direction_severity():
    prev = [_r("a", 0.7, "B — qualified")]
    curr = [_r("a", 0.3, "D — avoid")]
    al = alerts.tier_change_alerts(prev, curr)[0]
    assert al.kind == "tier_change" and al.severity == "warn"  # B → D is worse


def test_new_flag_is_critical():
    prev = [_r("a", 0.7, "B", [])]
    curr = [_r("a", 0.0, "D", ["dead_token"])]
    al = alerts.new_flag_alerts(prev, curr)[0]
    assert al.kind == "new_flag" and al.severity == "critical" and "dead_token" in al.message


def test_new_flag_not_refired_when_already_present():
    prev = [_r("a", 0.0, "D", ["dead_token"])]
    curr = [_r("a", 0.0, "D", ["dead_token"])]
    assert alerts.new_flag_alerts(prev, curr) == []


def test_unlock_and_narrative_thresholds():
    recs = [{"token": "x", "unlock_overhang": 0.8}, {"token": "y", "unlock_overhang": 0.2}]
    ua = alerts.unlock_alerts(recs, threshold=0.5)
    assert len(ua) == 1 and ua[0].subject == "x"

    cats = [{"name": "AI", "change_24h": 18.0}, {"name": "RWA", "change_24h": 3.0}]
    na = alerts.narrative_alerts(cats, threshold=10.0)
    assert len(na) == 1 and na[0].subject == "AI"


def test_evaluate_sorts_critical_first():
    prev = [_r("a", 0.7, "B", [])]
    curr = [_r("a", 0.5, "C", ["no_audit"])]  # both a new_flag (critical) and score_drop (warn)
    found = alerts.evaluate(prev, curr)
    assert found[0].severity == "critical"
    assert {a.kind for a in found} >= {"new_flag", "score_drop", "tier_change"}


def test_format_empty():
    assert alerts.format_alerts([]) == "no alerts"

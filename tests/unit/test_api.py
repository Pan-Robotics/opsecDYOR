"""Tests for the offline FastAPI endpoints (analyze/narratives hit the network)."""

import pytest
from fastapi.testclient import TestClient

from dyor.api.app import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_screener_sample():
    r = client.get("/api/screener", params={"source": "sample"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["results"]) > 0
    row = body["results"][0]
    assert {"token", "final_score", "tier", "coverage", "class", "domain_scores"} <= set(row)
    assert "label" in row["class"]


def test_screener_peer_groups_param():
    r = client.get("/api/screener", params={"source": "sample", "peer_groups": "true"})
    assert r.status_code == 200


def test_classes():
    r = client.get("/api/classes")
    names = {c["name"] for c in r.json()["classes"]}
    assert {"defi", "l1", "monetary", "meme", "stablecoin"} <= names


def test_methodology():
    body = client.get("/api/methodology").json()
    assert "weights" in body and "tiers" in body and "glossary" in body
    assert any(g["key"] == "price_to_fees" for g in body["glossary"])
    assert body["tiers"][0]["color"] in {"green", "blue", "orange", "red", "gray"}


def test_benchmark():
    body = client.get("/api/benchmark").json()
    assert body["total"] >= 4
    assert 0.0 <= body["accuracy"] <= 1.0


def test_analyze_validates_peer_mode():
    r = client.get("/api/analyze", params={"q": "aave", "peer_mode": "bogus"})
    assert r.status_code == 422  # pattern validation rejects it


def test_build_status_unknown_job():
    assert client.get("/api/screener/build/does-not-exist").json()["status"] == "unknown"


def test_jobs_status_unknown():
    from dyor.api.jobs import job_status
    assert job_status("nope") == {"status": "unknown"}


def test_screen_endpoint_offline():
    r = client.get("/api/screen", params={"source": "sample", "min_tier": "B", "no_flags": "true"})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body and body["universe"] > 0
    assert all(row["tier"][0] in ("A", "B") for row in body["results"])


def test_backtest_endpoint():
    # offline-safe: with no persisted runs it returns a note, else a tier table
    r = client.get("/api/backtest")
    assert r.status_code == 200
    assert "samples" in r.json()


def test_portfolio_endpoint_requires_tokens():
    assert client.get("/api/portfolio", params={"tokens": " , "}).status_code == 400


def test_chart_summary_empty():
    from dyor.api.serialize import chart_summary
    out = chart_summary([])
    assert out == {"prices": [], "first": None, "last": None, "change_pct": None}


def test_chart_summary_change_pct():
    from dyor.api.serialize import chart_summary
    out = chart_summary([[0, 100.0], [1, 110.0], [2, 120.0]])
    assert out["first"] == 100.0 and out["last"] == 120.0
    assert out["change_pct"] == 20.0
    assert len(out["prices"]) == 3


def test_chart_summary_downsamples_and_keeps_last():
    from dyor.api.serialize import chart_summary
    series = [[i, float(i)] for i in range(1000)]
    out = chart_summary(series, max_points=150)
    assert len(out["prices"]) < len(series)  # substantially downsampled
    assert out["prices"][-1] == [999, 999.0]  # last point preserved exactly
    assert out["last"] == 999.0

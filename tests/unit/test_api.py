"""Tests for the offline FastAPI endpoints (analyze/narratives hit the network)."""

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


def test_screener_build_is_disabled_without_admin_token(monkeypatch):
    from dyor.api import app as app_mod
    from dyor.config import Settings
    monkeypatch.setattr(app_mod, "get_settings", lambda: Settings(_env_file=None))
    assert client.post("/api/screener/build?top_n=30").status_code == 403


def test_screener_build_requires_matching_admin_token(monkeypatch):
    from dyor.api import app as app_mod, jobs
    from dyor.config import Settings
    monkeypatch.setattr(app_mod, "get_settings", lambda: Settings(admin_token="s3cret-token", _env_file=None))
    monkeypatch.setattr(jobs, "start_build", lambda top_n, category=None: "job-xyz")
    assert client.post("/api/screener/build", headers={"X-Admin-Token": "wrong"}).status_code == 403
    r = client.post("/api/screener/build", headers={"X-Admin-Token": "s3cret-token"})
    assert r.status_code == 200 and r.json()["job_id"] == "job-xyz"


def test_chart_rejects_non_coin_ids():
    assert client.get("/api/chart", params={"id": "../simple/price?ids=bitcoin"}).status_code == 422
    assert client.get("/api/chart", params={"id": "BITCOIN"}).status_code == 422


def test_portfolio_caps_holdings():
    r = client.get("/api/portfolio", params={"tokens": ",".join(f"t{i}" for i in range(11))})
    assert r.status_code == 422


def test_methodology_marks_inert_gate_rules():
    body = client.get("/api/methodology").json()
    g = body["gating"]
    assert g["extreme_fdv_mcap"]["active_on_open_data"] is True
    assert g["dead_token"]["active_on_open_data"] is True
    assert g["no_audit"]["active_on_open_data"] is True          # DefiLlama audit record
    assert g["unverified_contract"]["active_on_open_data"] is False
    assert g["anonymous_team"]["active_on_open_data"] is False


def test_build_job_unions_baskets_and_takes_the_collect_lock(monkeypatch, tmp_path):
    """The screener's Build button once replaced a 114-token board with 31."""
    import fcntl

    from dyor.api import jobs

    calls: dict = {}
    monkeypatch.setenv("DYOR_COLLECT_LOCK", str(tmp_path / "lock"))

    def fake_universe(top_n, category=None, include_baskets=False, **kw):
        calls["include_baskets"] = include_baskets
        return ["t"] * 3

    class FakeCollector:
        errors: list = []
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def collect(self, targets): return [{"token": f"t{i}"} for i in range(3)]

    monkeypatch.setattr("dyor.universe.fetch_universe", fake_universe)
    monkeypatch.setattr("dyor.collect.Collector", FakeCollector)
    jobs._run_build("j1", 3, None)
    assert calls["include_baskets"] is True
    assert jobs.job_status("j1")["status"] == "done"

    # a held lock (the cron) makes a build refuse rather than run concurrently
    with open(tmp_path / "lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        jobs._run_build("j2", 3, None)
    assert jobs.job_status("j2")["status"] == "error"
    assert "already running" in jobs.job_status("j2")["error"]


def test_analyze_persist_never_adds_unknown_tokens(monkeypatch):
    from dyor import analyze as an
    from dyor.store import db

    con = db.connect(); db.persist_records(con, [{"token": "aave", "x": 1}]); con.close()
    assert an._persist_live({"token": "aave", "x": 2}) is True
    assert an._persist_live({"token": "scamcoin", "x": 9}) is False
    con = db.connect(read_only=True)
    assert {r["token"] for r in db.latest_records(con)} == {"aave"}
    con.close()


def test_tokens_index_and_token_page_payloads():
    """The server-rendered /tokens and /token/<id> pages (and the sitemap and
    Open Graph images) read these; they must work without a live collect."""
    body = client.get("/api/tokens", params={"source": "sample"}).json()
    assert body["scale"] == 100 and body["count"] == len(body["tokens"]) > 0
    row = body["tokens"][0]
    assert {"id", "name", "symbol", "class_label", "final_score", "tier", "flags"} <= set(row)
    assert all(t["final_score"] is None or 0 <= t["final_score"] <= 100 for t in body["tokens"])
    tid = body["tokens"][0]["id"]
    d = client.get("/api/token", params={"id": tid, "source": "sample"}).json()
    assert d["scale"] == 100 and d["resolved"]["gecko_id"] == tid and d["on_board"] is True
    assert d["summary"] and "/100" in d["summary"] and d["explain"]["features"]
    assert d["source"]["kind"] == "stored" and d["score"]["final_score"] == row["final_score"]
    assert d["rank"] is not None and len(d["peers"]) <= 12
    assert client.get("/api/token", params={"id": "nope-not-here", "source": "sample"}).status_code == 404
    assert client.get("/api/token", params={"id": "../etc", "source": "sample"}).status_code == 422

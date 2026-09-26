from dyor.store import db


def test_persist_and_latest_records():
    con = db.connect(":memory:")
    db.persist_records(con, [{"token": "aave", "price_to_fees": 10.0}])
    run2 = db.persist_records(con, [
        {"token": "aave", "price_to_fees": 11.0},
        {"token": "uni", "price_to_fees": 80.0},
    ])
    latest = db.latest_records(con)
    assert {r["token"] for r in latest} == {"aave", "uni"}  # only the newest run
    assert any(r["price_to_fees"] == 11.0 for r in latest)
    # run ids are distinct (history preserved)
    runs = con.execute("SELECT COUNT(DISTINCT run_id) FROM token_records").fetchone()[0]
    assert runs == 2
    assert run2 == con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()[0]
    con.close()


def test_latest_records_empty_is_list():
    con = db.connect(":memory:")
    assert db.latest_records(con) == []
    con.close()


def test_upsert_into_latest_run_refreshes_without_new_run():
    con = db.connect(":memory:")
    db.persist_records(con, [
        {"token": "aave", "price_to_fees": 10.0},
        {"token": "uni", "price_to_fees": 80.0},
    ])
    # Live-analyze aave with fresh data → refresh in place.
    db.upsert_into_latest_run(con, {"token": "aave", "price_to_fees": 12.5})
    latest = db.latest_records(con)
    # Universe intact (no one-token run replacing it) and aave refreshed.
    assert {r["token"] for r in latest} == {"aave", "uni"}
    assert next(r for r in latest if r["token"] == "aave")["price_to_fees"] == 12.5
    # Still ONE run (refresh stayed under the latest run_id).
    assert con.execute("SELECT COUNT(DISTINCT run_id) FROM token_records").fetchone()[0] == 1
    con.close()


def test_upsert_into_latest_run_adds_new_token():
    con = db.connect(":memory:")
    db.persist_records(con, [{"token": "aave", "price_to_fees": 10.0}])
    db.upsert_into_latest_run(con, {"token": "rocket-pool", "price_to_fees": 15.0})
    assert {r["token"] for r in db.latest_records(con)} == {"aave", "rocket-pool"}
    con.close()


def test_upsert_into_latest_run_bootstraps_empty_store():
    con = db.connect(":memory:")
    db.upsert_into_latest_run(con, {"token": "aave", "price_to_fees": 10.0})
    assert {r["token"] for r in db.latest_records(con)} == {"aave"}
    con.close()


def test_runs_and_records_for_run_and_history():
    con = db.connect(":memory:")
    r1 = db.persist_records(con, [{"token": "aave", "price_to_fees": 20.0}])
    r2 = db.persist_records(con, [{"token": "aave", "price_to_fees": 10.0}])
    runs = db.runs(con)
    assert [rid for rid, _ in runs] == [r1, r2]  # oldest first
    assert db.records_for_run(con, r1)[0]["price_to_fees"] == 20.0

    from dyor.history import score_history

    hist = score_history(con, "aave")
    assert len(hist) == 2  # one score per run, oldest first
    assert all(isinstance(s, float) for _, s in hist)
    con.close()



def test_persist_run_refuses_a_drastic_shrink(sample_config):
    """A top-30 rebuild replaced a 114-token public screener on 2026-09-11."""
    import pytest

    con = db.connect(":memory:")
    db.persist_records(con, [{"token": f"t{i}"} for i in range(100)])
    with pytest.raises(db.RunShrinkRefused):
        db.persist_run(con, [{"token": "only"}], config=sample_config)
    assert len(db.latest_records(con)) == 100          # untouched
    db.persist_run(con, [{"token": f"t{i}"} for i in range(60)], config=sample_config)  # 60% ok
    assert len(db.latest_records(con)) == 60
    db.persist_run(con, [{"token": "only"}], config=sample_config, force=True)
    assert len(db.latest_records(con)) == 1
    con.close()


def test_persist_run_first_run_has_nothing_to_shrink(sample_config):
    con = db.connect(":memory:")
    db.persist_run(con, [{"token": "a"}], config=sample_config)
    assert len(db.latest_records(con)) == 1
    con.close()


def test_refresh_in_latest_run_only_touches_tokens_on_the_board():
    """The public analyze endpoint must not insert arbitrary tokens."""
    con = db.connect(":memory:")
    db.persist_records(con, [{"token": "aave", "price_to_fees": 10.0}])
    assert db.refresh_in_latest_run(con, {"token": "aave", "price_to_fees": 12.0}) is True
    assert db.refresh_in_latest_run(con, {"token": "scamcoin", "price_to_fees": 0.1}) is False
    latest = db.latest_records(con)
    assert {r["token"] for r in latest} == {"aave"}
    assert latest[0]["price_to_fees"] == 12.0
    con.close()


def test_prune_runs_keeps_newest():
    con = db.connect(":memory:")
    for i in range(5):
        db.persist_records(con, [{"token": "a", "i": i}])
    assert db.prune_runs(con, keep=2) == 3
    kept = [r for r, _ in db.runs(con)]
    assert len(kept) == 2
    assert db.latest_records(con)[0]["i"] == 4
    assert db.prune_runs(con, keep=0) == 0            # keep=0 is a no-op, never wipes
    con.close()


def test_read_only_connect_falls_back_before_first_write(tmp_path):
    path = tmp_path / "x.duckdb"
    con = db.connect(path, read_only=True)               # file absent → normal open + DDL
    assert db.latest_records(con) == []
    con.close()
    con = db.connect(path); db.persist_records(con, [{"token": "a"}]); con.close()
    ro = db.connect(path, read_only=True)
    assert [r["token"] for r in db.latest_records(ro)] == ["a"]
    import duckdb
    import pytest
    with pytest.raises(duckdb.Error):                       # genuinely read-only
        db.persist_records(ro, [{"token": "b"}])
    ro.close()

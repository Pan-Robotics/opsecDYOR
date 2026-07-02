from dyor.store import db


def test_land_and_read_latest():
    con = db.connect(":memory:")
    db.land_raw(con, "defillama", "protocols", [{"slug": "aave"}])
    db.land_raw(con, "defillama", "protocols", [{"slug": "aave-v3"}])
    latest = db.latest_raw(con, "defillama", "protocols")
    assert latest == [{"slug": "aave-v3"}]  # most recent wins
    con.close()


def test_latest_raw_missing_is_none():
    con = db.connect(":memory:")
    assert db.latest_raw(con, "nope", "nope") is None
    con.close()


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


def test_upsert_crosswalk_replaces():
    con = db.connect(":memory:")
    rows = [{
        "chain_address": "ethereum:0xabc", "chain": "ethereum", "address": "0xabc",
        "gecko_id": "foo", "defillama_slug": None, "cmc_id": None,
        "symbol": "foo", "name": "Foo",
    }]
    assert db.upsert_crosswalk(con, rows) == 1
    rows[0]["defillama_slug"] = "foo-protocol"
    db.upsert_crosswalk(con, rows)
    got = con.execute(
        "SELECT defillama_slug FROM crosswalk WHERE chain_address = 'ethereum:0xabc'"
    ).fetchone()
    assert got[0] == "foo-protocol"  # replaced, not duplicated
    count = con.execute("SELECT COUNT(*) FROM crosswalk").fetchone()[0]
    assert count == 1
    con.close()

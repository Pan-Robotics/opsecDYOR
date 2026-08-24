"""`dyor` command-line entry point.

  dyor score                    # score the built-in sample universe
  dyor score --json recs.json   # score a JSON array of token records
  dyor score --format json      # machine-readable output
  dyor collect                  # LIVE: fetch DefiLlama + CoinGecko, then score
"""

from __future__ import annotations

import argparse
import json
import math
import sys

from dyor.pipeline import score_universe
from dyor.sample_data import SAMPLE_UNIVERSE


def _fmt(x: float) -> str:
    return "  n/a" if math.isnan(x) else f"{x:5.3f}"


def _print_table(results) -> None:
    header = f"{'TOKEN':<18} {'RAW':>6} {'FINAL':>6} {'COV':>5}  {'TIER':<22} FLAGS"
    print(header)
    print("-" * len(header))
    for r in results:
        flags = ", ".join(r.flags) if r.flags else "—"
        cov = "  n/a" if math.isnan(r.coverage) else f"{r.coverage:4.0%}"
        print(f"{r.token:<18} {_fmt(r.raw_score):>6} {_fmt(r.final_score):>6} {cov:>5}  "
              f"{r.tier:<22} {flags}")
        for note in r.advisories:
            print(f"{'':<18} ⚠ {note}")


def _to_dict(r) -> dict:
    return {
        "token": r.token,
        "raw_score": None if math.isnan(r.raw_score) else round(r.raw_score, 4),
        "final_score": None if math.isnan(r.final_score) else round(r.final_score, 4),
        "tier": r.tier,
        "flags": r.flags,
        "advisories": r.advisories,
        "coverage": None if math.isnan(r.coverage) else round(r.coverage, 3),
        "features_present": r.features_present,
        "features_total": r.features_total,
        "domain_scores": {
            k: (None if math.isnan(v) else round(v, 4))
            for k, v in r.domain_scores.items()
        },
    }


def _cmd_score(args: argparse.Namespace) -> int:
    if args.json:
        with open(args.json, "r", encoding="utf-8") as fh:
            records = json.load(fh)
    else:
        records = SAMPLE_UNIVERSE

    results = score_universe(records)

    if args.format == "json":
        json.dump([_to_dict(r) for r in results], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_table(results)
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    # Imported lazily so `dyor score` has no network/client import cost.
    from dyor.collect import Collector

    targets = None
    if args.top_n or args.category:
        from dyor.universe import fetch_universe

        targets = fetch_universe(
            top_n=args.top_n or 50, category=args.category, use_cache=not args.no_cache,
            include_baskets=args.include_baskets)
        print(f"built universe of {len(targets)} targets"
              + (f" in category '{args.category}'" if args.category else ""), file=sys.stderr)

    with Collector(use_cache=not args.no_cache) as collector:
        records = collector.collect(targets)
        errors = collector.errors

    if errors:
        print(f"⚠ {len(errors)} feed failure(s):", file=sys.stderr)
        for e in errors:
            print(f"    {e['token']:<16} {e['source']:<11} {e['error']}", file=sys.stderr)

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)

    if args.persist:
        from dyor.store import db

        con = db.connect()
        run_id = db.persist_records(con, records)
        con.close()
        print(f"persisted {len(records)} records as run {run_id}", file=sys.stderr)

    results = score_universe(records, peer_groups=args.peer_groups)
    if args.format == "json":
        json.dump([_to_dict(r) for r in results], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_table(results)
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    """One unit of scheduled work: snapshot previous → collect+persist → alert.

    Designed to be run by cron/systemd-timer:  */30 * * * *  dyor refresh
    """
    from dyor import alerts
    from dyor.collect import Collector
    from dyor.store import db

    # DuckDB is single-writer ACROSS PROCESSES: a second process cannot open the
    # file read-write at all. So read the previous run and release the lock
    # immediately — holding it through the (20+ minute) collect below would lock
    # the API out of the store for the whole run, breaking the screener and
    # silently emptying analyze's peer set.
    con = db.connect()
    try:
        prev_records = db.latest_records(con)
    finally:
        con.close()
    prev_results = score_universe(prev_records)  # last run (may be empty)

    targets = None
    if args.top_n or args.category:
        from dyor.universe import fetch_universe
        targets = fetch_universe(top_n=args.top_n or 50, category=args.category,
                                 include_baskets=not args.no_baskets)

    with Collector() as collector:
        records = collector.collect(targets)
        errors = collector.errors

    if not records:
        # Persisting an empty run would make it the "latest" one and blank the
        # screener. A collect that returns nothing is a failure, not a result.
        print("refresh: collect returned no records — nothing persisted", file=sys.stderr)
        return 1

    con = db.connect()
    try:
        run_id = db.persist_records(con, records)
    finally:
        con.close()

    curr_results = score_universe(records)

    narratives = None
    if not args.no_narratives:
        from dyor.narratives import fetch_narratives
        narratives = _try(lambda: fetch_narratives(top=50))

    found = alerts.evaluate(prev_results, curr_results, records=records, narratives=narratives)
    print(f"refresh: run {run_id}, {len(records)} tokens, {len(errors)} feed error(s), "
          f"{len(found)} alert(s)", file=sys.stderr)
    alerts.emit(found)
    return 0


def _try(fn):
    try:
        return fn()
    except Exception:
        return None


def _cmd_analyze(args: argparse.Namespace) -> int:
    from dyor.analyze import analyze_token

    res = analyze_token(args.query, peer_mode=args.peer_mode, use_cache=not args.no_cache)
    if res.resolved is None:
        print(f"could not resolve '{args.query}'", file=sys.stderr)
        return 2

    r = res.resolved
    print(f"resolved: {r.name} ({r.symbol})  id={r.gecko_id}  "
          f"matched by {r.matched_by}" + (f"  rank #{r.market_cap_rank}" if r.market_cap_rank else ""))
    if r.chains:
        print(f"chains:   {', '.join(r.chains[:8])}" + (" …" if len(r.chains) > 8 else ""))
    if not res.ok:
        print("no market data — could not score", file=sys.stderr)
        return 2

    from dyor.classes import class_profile
    cls = class_profile((res.record or {}).get("_class"))
    print(f"class:    {cls.label} — {cls.description}")

    sr = res.result
    cov = "n/a" if math.isnan(sr.coverage) else f"{sr.coverage:.0%}"
    print(f"\nscore:    {_fmt(sr.final_score)}  ({sr.tier})   coverage {cov}   "
          f"vs {res.peer_count} peers")
    if sr.flags:
        print(f"flags:    {', '.join(sr.flags)}")
    for note in sr.advisories:
        print(f"          ⚠ {note}")
    if args.format == "json":
        json.dump(_to_dict(sr), sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


def _cmd_reference(args: argparse.Namespace) -> int:
    from dyor.reference import build_references

    counts = build_references(use_cache=not args.no_cache)
    for cls, n in counts.items():
        print(f"  {cls:<12} {n} reference tokens cached", file=sys.stderr)
    print(f"reference baskets built: {sum(counts.values())} tokens across "
          f"{len([c for c in counts.values() if c])} classes", file=sys.stderr)
    return 0


def _cmd_memo(args: argparse.Namespace) -> int:
    from dyor.memo import analyst_memo
    print(analyst_memo(args.query, peer_mode=args.peer_mode))
    return 0


def _cmd_screen(args: argparse.Namespace) -> int:
    from dyor.screen import screen
    from dyor.store import db
    con = db.connect()
    records = db.latest_records(con) if args.source == "stored" else SAMPLE_UNIVERSE
    con.close()
    fmin = {"real_yield": args.min_real_yield} if args.min_real_yield is not None else None
    fmax = {"fdv_mcap_ratio": args.max_fdv_mcap} if args.max_fdv_mcap is not None else None
    rows = screen(records, asset_class=args.asset_class, min_tier=args.min_tier,
                  min_score=args.min_score, no_flags=args.no_flags,
                  feature_min=fmin, feature_max=fmax, limit=args.limit)
    print(f"{'TOKEN':<18}{'CLASS':<14}{'SCORE':>6} {'TIER':<8} CONF")
    for r in rows:
        sc = "  n/a" if r["score"] is None else f"{r['score']:.3f}"
        print(f"{r['token']:<18}{str(r['class']):<14}{sc:>6} {r['tier'][:1]:<8} {r['confidence']}")
    print(f"\n{len(rows)} match of {len(records)}", file=sys.stderr)
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    from dyor.backtest import backtest
    json.dump(backtest(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_barbell(args: argparse.Namespace) -> int:
    from dyor.portfolio import barbell
    json.dump(barbell(n_satellites=args.n), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from dyor.benchmark import DEFAULT_CASES, run_benchmark

    report = run_benchmark(DEFAULT_CASES)
    for r in report.results:
        mark = "✓" if r.passed else "✗"
        print(f"  {mark} {r.name:<22} {r.tier:<22} "
              + ("" if r.passed else "— " + "; ".join(r.reasons)))
    print(f"\nbenchmark: {report.passed}/{report.total} passed "
          f"({report.accuracy:.0%})", file=sys.stderr)
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dyor", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="analyze ONE token by name, symbol, or contract address")
    analyze.add_argument("query", help="token name, symbol, or contract address (EVM/Solana)")
    analyze.add_argument("--peer-mode", default="class", choices=["class", "stored", "sample", "category"],
                         help="peer baseline: class (same asset class, fairest) | stored | sample | category")
    analyze.add_argument("--no-cache", action="store_true", help="bypass the on-disk response cache")
    analyze.add_argument("--format", choices=["text", "json"], default="text")
    analyze.set_defaults(func=_cmd_analyze)

    bench = sub.add_parser("benchmark", help="check the scorer reproduces known good/bad calls")
    bench.set_defaults(func=_cmd_benchmark)

    ref = sub.add_parser("reference", help="build cached same-class peer baskets (for analyze --peer-mode class)")
    ref.add_argument("--no-cache", action="store_true", help="bypass the on-disk response cache")
    ref.set_defaults(func=_cmd_reference)

    memo = sub.add_parser("memo", help="reasoned analyst memo for a token")
    memo.add_argument("query")
    memo.add_argument("--peer-mode", default="class", choices=["class", "stored", "sample", "category"])
    memo.set_defaults(func=_cmd_memo)

    screen = sub.add_parser("screen", help="filter the saved/sample universe by criteria")
    screen.add_argument("--source", default="stored", choices=["stored", "sample"])
    screen.add_argument("--asset-class")
    screen.add_argument("--min-tier", choices=["A", "B", "C", "D"])
    screen.add_argument("--min-score", type=float)
    screen.add_argument("--min-real-yield", type=float)
    screen.add_argument("--max-fdv-mcap", type=float)
    screen.add_argument("--no-flags", action="store_true")
    screen.add_argument("--limit", type=int, default=25)
    screen.set_defaults(func=_cmd_screen)

    bt = sub.add_parser("backtest", help="per-tier forward return from persisted runs")
    bt.set_defaults(func=_cmd_backtest)

    bb = sub.add_parser("barbell", help="BTC anchor + top-N qualified satellites from the saved universe")
    bb.add_argument("-n", type=int, default=5)
    bb.set_defaults(func=_cmd_barbell)

    refresh = sub.add_parser("refresh", help="collect + persist + alert vs the previous run (for cron)")
    refresh.add_argument("--top-n", type=int, help="build a top-N universe instead of the curated set")
    refresh.add_argument("--category", help="restrict the built universe to one category")
    refresh.add_argument("--no-narratives", action="store_true", help="skip the narrative-rotation alert pass")
    refresh.add_argument("--no-baskets", action="store_true",
                         help="don't pin the class reference baskets into the universe "
                              "(by default they are unioned in, so the screener keeps the "
                              "majors and every asset class regardless of TVL churn)")
    refresh.set_defaults(func=_cmd_refresh)

    score = sub.add_parser("score", help="score a token universe")
    score.add_argument("--json", help="path to a JSON array of token records")
    score.add_argument("--format", choices=["table", "json"], default="table")
    score.set_defaults(func=_cmd_score)

    collect = sub.add_parser("collect", help="LIVE: fetch + score the default DeFi universe")
    collect.add_argument("--format", choices=["table", "json"], default="table")
    collect.add_argument("--no-cache", action="store_true", help="bypass the on-disk response cache")
    collect.add_argument("--dump", help="also write the raw collected records to this JSON path")
    collect.add_argument("--persist", action="store_true", help="persist records to the DuckDB store")
    collect.add_argument("--top-n", type=int, help="build a universe of the top-N protocols by TVL (else the curated DeFi set)")
    collect.add_argument("--category", help="restrict the built universe to one DefiLlama category (e.g. Lending)")
    collect.add_argument("--peer-groups", action="store_true", help="normalize within category instead of across the whole universe")
    collect.add_argument("--include-baskets", action="store_true",
                         help="union the class reference baskets into the built universe")
    collect.set_defaults(func=_cmd_collect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# Run on the server: /root/DYOR/.venv/bin/python deploy/coverage-matrix.py
"""Why is each feature None? Per-class, per-feature coverage with the reason.

Reads the latest persisted run (read-only). For every token and every feature in
its class spec: present → ok; else attribute the gap to its source's `_feeds`
status (off / empty / error), to "no source" (features nothing computes), or to
"derived-null" (the source was ok but the derivation produced None — e.g.
holdersRevenue empty → real_yield None).
"""
from collections import Counter, defaultdict
from dyor.store import db
from dyor.classes import class_profile

SOURCE = {
    "price_to_fees": "defillama", "price_to_sales": "defillama", "mc_tvl": "defillama",
    "real_yield": "defillama", "value_accrual": "defillama",
    "fdv_mcap_ratio": "coingecko", "float_ratio": "coingecko", "social_sentiment": "coingecko",
    "unlock_overhang": "cryptorank", "unlock_pct_of_volume": "cryptorank",
    "top10_concentration": "ethplorer",
    "address_growth": "santiment", "dev_commit_trend": "santiment", "social_trend": "santiment",
    "inflation_rate": None, "reserve_trend": None,   # nothing computes these
}

con = db.connect(read_only=True)
runs = db.runs(con); rid = runs[-1][0]
recs = db.records_for_run(con, rid); con.close()
print(f"run {rid}: {len(recs)} tokens\n")

by_class = defaultdict(list)
for r in recs: by_class[r.get("_class")].append(r)

grand = Counter(); grand_n = 0
print(f"{'class':11} {'feature':22} {'present':>8} {'off':>5} {'empty':>6} {'error':>6} {'no-src':>7} {'derived-null':>13}")
print("-" * 86)
for cls, rows in sorted(by_class.items()):
    prof = class_profile(cls)
    feats = [f for fs in prof.feature_spec.values() for f, _ in fs]
    for f in feats:
        c = Counter()
        for r in rows:
            if r.get(f) is not None:
                c["present"] += 1; continue
            src = SOURCE.get(f)
            if src is None: c["no-src"] += 1; continue
            st = (r.get("_feeds") or {}).get(src, "off")
            if st == "ok": c["derived-null"] += 1
            else: c[st] += 1
        n = len(rows); pct = 100 * c["present"] / n
        flag = "" if pct >= 80 else ("  <- weak" if pct >= 40 else "  <- MISSING")
        print(f"{cls:11} {f:22} {c['present']:>4}/{n:<3} {c['off']:>5} {c['empty']:>6} {c['error']:>6} {c['no-src']:>7} {c['derived-null']:>13}{flag}")
        grand.update(c); grand_n += n
    print()

print("=== per-token coverage distribution (class-relative) ===")
buckets = Counter()
worst = []
for r in recs:
    prof = class_profile(r.get("_class")); feats = [f for fs in prof.feature_spec.values() for f, _ in fs]
    cov = sum(1 for f in feats if r.get(f) is not None) / len(feats)
    buckets[f"{int(cov*10)*10:>3}%"] += 1
    worst.append((cov, r["token"], r.get("_class"), r.get("_feeds")))
for k in sorted(buckets): print(f"   {k}: {buckets[k]}")
print("\n=== 8 thinnest tokens ===")
for cov, t, cls, feeds in sorted(worst)[:8]:
    print(f"   {t:26} {cls:10} {cov:.0%}  feeds={ {k:v for k,v in (feeds or {}).items() if v!='ok'} }")
print("\n=== overall feature-slot outcome ===")
tot = sum(grand.values())
for k, v in grand.most_common(): print(f"   {k:13} {v:5}  {100*v/tot:5.1f}%")

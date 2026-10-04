"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api, type TokenDetail } from "@/lib/api";
import { fmt, ScoreBar, Spinner, TierBadge } from "@/components/ui";
import { useAppStateHydrated, useStickyState } from "@/components/AppState";
import { METRICS, fmtMetric, metricByKey, type Metric } from "@/lib/metrics";

const CLASSES = ["defi", "l1", "monetary", "meme", "stablecoin"];
const PRESETS: { label: string; metric: string; order: "best" | "worst" }[] = [
  { label: "Best real yield", metric: "real_yield", order: "best" },
  { label: "Cheapest on fees", metric: "price_to_fees", order: "best" },
  { label: "Strongest tokenomics", metric: "tokenomics", order: "best" },
  { label: "Strongest fundamentals", metric: "fundamental", order: "best" },
  { label: "Most concentrated holders", metric: "top10_concentration", order: "worst" },
  { label: "Biggest dilution overhang", metric: "fdv_mcap_ratio", order: "worst" },
  { label: "Fastest address growth", metric: "address_growth", order: "best" },
  { label: "Most dev activity", metric: "dev_activity", order: "best" },
];

function metricValue(row: TokenDetail, m: Metric): number | null {
  if (m.kind === "score") return row.final_score;
  if (m.kind === "domain") return row.domain_scores?.[m.key] ?? null;
  const v = row.features?.[m.key];
  return typeof v === "number" ? v : null;
}
function metricPercentile(row: TokenDetail, m: Metric): number | null {
  if (m.kind === "feature") return row.percentiles?.[m.key] ?? null;
  return null;
}

export default function ScreenerPage() {
  const hydrated = useAppStateHydrated();
  const [error, setError] = useState<string | null>(null);
  const [peerGroups, setPeerGroups] = useStickyState("screener:peerGroups", false);
  const [penalize, setPenalize] = useStickyState("screener:penalize", true);
  // The loaded board stays in memory for the tab (not in storage: it is bulky and
  // cheap to refetch), so coming back from Compare or a token page is instant.
  type Board = { rows: TokenDetail[]; run: string | null; at: string | null };
  const [board, setBoard] = useStickyState<Board | null>(`cache:screener:${peerGroups ? 1 : 0}${penalize ? 1 : 0}`, null);
  const rows = board?.rows ?? null;
  const meta = { run: board?.run ?? null, at: board?.at ?? null };

  const [metricKey, setMetricKey] = useStickyState("screener:metric", "final_score");
  const [order, setOrder] = useStickyState<"best" | "worst">("screener:order", "best");
  const [fClass, setFClass] = useStickyState("screener:fClass", "");
  const [fTier, setFTier] = useStickyState("screener:fTier", "");
  const [fFlags, setFFlags] = useStickyState<"any" | "none" | "flagged">("screener:fFlags", "any");
  const [minCov, setMinCov] = useStickyState("screener:minCov", "");
  const [query, setQuery] = useStickyState("screener:q", "");
  const [selected, setSelected] = useStickyState<string[]>("screener:selected", []);

  const load = useCallback(async () => {
    setBoard(null); setError(null);
    try {
      const d = await api.tokensDetail(peerGroups, penalize);
      setBoard({ rows: d.tokens, run: d.run_id, at: d.collected_at });
    } catch (e: any) { setError(e.message); }
  }, [peerGroups, penalize, setBoard]);
  // First load waits for the tab's stored state (the toggles above may differ from the defaults).
  useEffect(() => { if (hydrated && !board) load(); }, [hydrated, board, load]);

  const metric = metricByKey(metricKey) ?? METRICS[0];
  const bestFirst = order === "best";

  const view = useMemo(() => {
    if (!rows) return [];
    const q = query.trim().toLowerCase();
    const cov = minCov === "" ? null : Number(minCov);
    const kept = rows.filter((r) => {
      if (fClass && r.class !== fClass) return false;
      if (fTier && !r.tier.trim().startsWith(fTier)) return false;
      if (fFlags === "none" && r.flags.length) return false;
      if (fFlags === "flagged" && !r.flags.length) return false;
      if (cov !== null && (r.coverage === null || r.coverage < cov)) return false;
      if (q && !(`${r.name} ${r.symbol} ${r.id}`.toLowerCase().includes(q))) return false;
      return true;
    });
    const sign = (metric.higherIsBetter ? 1 : -1) * (bestFirst ? -1 : 1); // -1 → descending when best & higher-is-better
    return kept
      .map((r) => ({ r, v: metricValue(r, metric), p: metricPercentile(r, metric) }))
      .sort((a, b) => {
        if (a.v === null && b.v === null) return 0;
        if (a.v === null) return 1;
        if (b.v === null) return -1;
        return sign * (a.v - b.v);
      });
  }, [rows, query, minCov, fClass, fTier, fFlags, metric, bestFirst]);

  const withValue = view.filter((x) => x.v !== null).length;
  const toggle = (id: string) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id].slice(-6));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Screener</h1>
          <p className="mt-1 max-w-3xl text-muted">
            Rank the whole board by the composite, by a single domain, or by one metric (best or worst first), then narrow by class,
            tier, gate flags and data coverage. Tick tokens to compare them line for line.
            {meta.at ? ` Board run of ${meta.at.slice(0, 10)}.` : ""}
          </p>
        </div>
        <button onClick={load} className="rounded-lg border border-edge px-3 py-1.5 text-sm text-white hover:bg-panel2">Reload</button>
      </div>

      {/* presets */}
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => {
          const active = p.metric === metricKey && p.order === order;
          return (
            <button key={p.label} onClick={() => { setMetricKey(p.metric); setOrder(p.order); }}
              className={`pill border ${active ? "border-brand bg-brand/15 text-white" : "border-edge text-muted hover:text-white"}`}>
              {p.label}
            </button>
          );
        })}
      </div>

      {/* controls */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1 text-xs text-muted">Rank by
            <select value={metricKey} onChange={(e) => setMetricKey(e.target.value)}
              className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white">
              <optgroup label="Composite">{METRICS.filter((m) => m.kind === "score").map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</optgroup>
              <optgroup label="Domains">{METRICS.filter((m) => m.kind === "domain").map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</optgroup>
              <optgroup label="Metrics">{METRICS.filter((m) => m.kind === "feature").map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</optgroup>
            </select>
          </label>
          <div className="flex flex-col gap-1 text-xs text-muted">Order
            <div className="flex overflow-hidden rounded-lg border border-edge">
              {(["best", "worst"] as const).map((o) => (
                <button key={o} onClick={() => setOrder(o)}
                  className={`px-3 py-1.5 text-sm ${order === o ? "bg-brand/15 text-white" : "text-muted hover:text-white"}`}>
                  {o === "best" ? "Best first" : "Worst first"}
                </button>
              ))}
            </div>
          </div>
          <label className="flex flex-col gap-1 text-xs text-muted">Class
            <select value={fClass} onChange={(e) => setFClass(e.target.value)} className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white">
              <option value="">any</option>{CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">Tier
            <select value={fTier} onChange={(e) => setFTier(e.target.value)} className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white">
              <option value="">any</option>{["A", "B", "C", "D"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">Gate flags
            <select value={fFlags} onChange={(e) => setFFlags(e.target.value as any)} className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white">
              <option value="any">any</option><option value="none">none</option><option value="flagged">flagged only</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">Min coverage %
            <input value={minCov} onChange={(e) => setMinCov(e.target.value)} placeholder="e.g. 60" inputMode="numeric"
              className="w-24 rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white" />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs text-muted">Search
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="name, symbol or id"
              className="min-w-40 rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white" />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
          <span>{metric.blurb} {metric.kind === "feature" ? (metric.higherIsBetter ? "Higher is better." : "Lower is better.") : ""}</span>
          <label className="ml-auto flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={peerGroups} onChange={(e) => setPeerGroups(e.target.checked)} /> rank within category
          </label>
          <label className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={penalize} onChange={(e) => setPenalize(e.target.checked)} /> penalize missing core
          </label>
        </div>
      </div>

      {/* compare tray */}
      {selected.length > 0 && (
        <div className="card flex flex-wrap items-center gap-3 border-brand/40 bg-brand/5 text-sm">
          <span className="text-white">{selected.length} selected:</span>
          {selected.map((id) => (
            <button key={id} onClick={() => toggle(id)} className="pill border border-edge bg-panel2 text-white hover:border-rose-400/60" title="remove">{id} x</button>
          ))}
          <Link href={`/compare?tokens=${encodeURIComponent(selected.join(","))}`} className="btn ml-auto">Compare selected</Link>
          <button onClick={() => setSelected([])} className="text-xs text-muted hover:text-white">clear</button>
        </div>
      )}

      {!rows && !error && <div className="card"><Spinner /></div>}
      {error && <div className="card border-rose-500/30 text-rose-200">{error}</div>}
      {rows && rows.length === 0 && (
        <div className="card text-muted">No saved universe yet. The weekly refresh has not run on this instance.</div>
      )}

      {rows && rows.length > 0 && (
        <div className="card !p-0 overflow-x-auto">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-edge px-3 py-2 text-xs text-muted">
            <span>{view.length} of {rows.length} tokens{metric.kind !== "score" ? `, ${withValue} with a ${metric.label.toLowerCase()} value` : ""}</span>
            <span>Sorted by {metric.label.toLowerCase()}, {bestFirst ? "best" : "worst"} first. Tokens without the value are listed last.</span>
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted">
              <tr className="border-b border-edge">
                <th className="p-3 w-8">#</th>
                <th className="p-3 w-8"><span className="sr-only">compare</span></th>
                <th className="p-3">Token</th>
                <th className="p-3">Class</th>
                <th className="p-3 w-44">Score</th>
                <th className="p-3">Tier</th>
                {metric.kind !== "score" && <th className="p-3">{metric.label}</th>}
                <th className="p-3">Coverage</th>
                <th className="p-3">Flags</th>
              </tr>
            </thead>
            <tbody>
              {view.map(({ r, v, p }, i) => (
                <tr key={r.id} className={`border-b border-edge/60 hover:bg-panel2/40 ${v === null && metric.kind !== "score" ? "text-muted" : ""}`}>
                  <td className="p-3 text-muted">{i + 1}</td>
                  <td className="p-3"><input type="checkbox" aria-label={`compare ${r.name}`} checked={selected.includes(r.id)} onChange={() => toggle(r.id)} /></td>
                  <td className="p-3 font-medium">
                    <Link href={`/token/${encodeURIComponent(r.id)}`} className="text-white hover:text-brand">{r.name}</Link>
                    {r.symbol && <span className="ml-1 text-xs text-muted">{r.symbol}</span>}
                  </td>
                  <td className="p-3 text-muted">{r.class_label}</td>
                  <td className="p-3"><div className="flex items-center gap-2"><ScoreBar value={r.final_score} /><span className="w-12 text-right tabular-nums">{fmt(r.final_score)}</span></div></td>
                  <td className="p-3"><TierBadge tier={r.tier} /></td>
                  {metric.kind !== "score" && (
                    <td className="p-3 tabular-nums">
                      <span className="text-white">{fmtMetric(v, metric.unit)}</span>
                      {p !== null && <span className="ml-2 text-xs text-muted">pct {Math.round(p)}</span>}
                    </td>
                  )}
                  <td className="p-3 tabular-nums text-muted">{r.coverage === null ? "n/a" : `${Math.round(r.coverage)}%`}</td>
                  <td className="p-3 text-xs text-rose-300">{r.flags.join(", ") || "none"}</td>
                </tr>
              ))}
              {view.length === 0 && <tr><td colSpan={9} className="p-4 text-center text-muted">No tokens match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-muted">
        Every row links to the token&apos;s permanent page with the full ledger. Scores and percentiles are 0 to 100 against same-class
        peers; metric values are the raw figures. For a token not on the board, <Link href="/analyze" className="text-brand hover:text-brand2">analyze it live</Link>.
      </p>
    </div>
  );
}

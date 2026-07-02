"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type BuildJob, type Score, type ScreenRow } from "@/lib/api";
import { fmt, ScoreBar, Spinner, TierBadge } from "@/components/ui";
import TokenLink from "@/components/TokenLink";
import { useStickyState } from "@/components/AppState";

const TIERS: [string, string][] = [
  ["A", "high conviction"],
  ["B", "qualified"],
  ["C", "watchlist"],
  ["D", "avoid"],
];
const PER_TIER = 20;

export default function ScreenerPage() {
  const [source, setSource] = useStickyState("screener:source", "stored");
  const [peerGroups, setPeerGroups] = useStickyState("screener:peerGroups", false);
  const [penalize, setPenalize] = useStickyState("screener:penalize", true);
  const [rows, setRows] = useState<Score[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTier, setActiveTier] = useStickyState("screener:tier", "A");

  // build job
  const [topN, setTopN] = useStickyState("screener:topN", 30);
  const [job, setJob] = useState<BuildJob | null>(null);
  const polling = useRef<ReturnType<typeof setTimeout> | null>(null);

  // filter (screen_for)
  const [fClass, setFClass] = useStickyState("screener:fClass", "");
  const [fTier, setFTier] = useStickyState("screener:fTier", "");
  const [fYield, setFYield] = useStickyState("screener:fYield", "");
  const [fNoFlags, setFNoFlags] = useStickyState("screener:fNoFlags", false);
  const [filtered, setFiltered] = useStickyState<{ rows: ScreenRow[]; universe: number } | null>("screener:filtered", null);

  async function applyFilter() {
    const params: Record<string, string> = { source };
    if (fClass) params.asset_class = fClass;
    if (fTier) params.min_tier = fTier;
    if (fYield) params.min_real_yield = String(Number(fYield) / 100);
    if (fNoFlags) params.no_flags = "true";
    const d = await api.screenFilter(params);
    setFiltered({ rows: d.results, universe: d.universe });
  }

  const load = useCallback(async () => {
    setRows(null);
    setError(null);
    try {
      const d = await api.screener(source, peerGroups, penalize);
      setRows(d.results);
    } catch (e: any) {
      setError(e.message);
    }
  }, [source, peerGroups, penalize]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => () => { if (polling.current) clearTimeout(polling.current); }, []);

  async function startBuild() {
    setJob({ status: "running", elapsed: 0 });
    try {
      const { job_id } = await api.screenerBuild(topN);
      const poll = async () => {
        const s = await api.screenerBuildStatus(job_id);
        setJob(s);
        if (s.status === "running") {
          polling.current = setTimeout(poll, 3000);
        } else if (s.status === "done") {
          setSource("stored");
          await load();
        }
      };
      poll();
    } catch (e: any) {
      setJob({ status: "error", error: e.message });
    }
  }

  const byTier: Record<string, Score[]> = { A: [], B: [], C: [], D: [] };
  (rows ?? []).forEach((r) => {
    const k = r.tier?.trim()?.[0];
    if (byTier[k]) byTier[k].push(r);
  });
  const active = (byTier[activeTier] ?? []).slice(0, PER_TIER);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">📊 Screener</h1>
          <p className="mt-1 text-muted">
            A scored universe, grouped by tier. Build a fresh top-N by TVL, or read your last saved run.
          </p>
        </div>
        <button onClick={load} className="rounded-lg border border-edge px-3 py-1.5 text-sm text-white hover:bg-panel2">
          ↻ Refresh
        </button>
      </div>

      {/* controls */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {[["stored", "Saved run"], ["sample", "Sample set"]].map(([v, l]) => (
            <button key={v} onClick={() => setSource(v)}
              className={`pill border ${source === v ? "border-brand bg-brand/15 text-white" : "border-edge text-muted hover:text-white"}`}>
              {l}
            </button>
          ))}
          <label className="ml-2 flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={peerGroups} onChange={(e) => setPeerGroups(e.target.checked)} /> within category
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={penalize} onChange={(e) => setPenalize(e.target.checked)} /> penalize missing core
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-edge pt-3">
          <span className="text-xs text-muted">Build fresh universe — top</span>
          <input type="number" min={5} max={80} value={topN}
            onChange={(e) => setTopN(Math.max(5, Math.min(80, Number(e.target.value) || 30)))}
            className="w-20 rounded-lg border border-edge bg-panel2 px-2 py-1 text-sm text-white" />
          <span className="text-xs text-muted">by TVL</span>
          <button onClick={startBuild} disabled={job?.status === "running"} className="btn">
            {job?.status === "running" ? "Building…" : "Build / refresh search"}
          </button>
          {job?.status === "running" && (
            <span className="flex items-center gap-2 text-xs text-muted">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-edge border-t-brand" />
              collecting {job.target_count ?? topN} tokens… {job.elapsed ? `${job.elapsed}s` : ""} (a few minutes)
            </span>
          )}
          {job?.status === "done" && <span className="text-xs text-emerald-300">✓ built {job.count} tokens</span>}
          {job?.status === "error" && <span className="text-xs text-rose-300">build failed: {job.error}</span>}
        </div>
      </div>

      {/* filter (screen) */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-3 text-sm">
          <label className="flex flex-col gap-1 text-xs text-muted">Class
            <select value={fClass} onChange={(e) => setFClass(e.target.value)}
              className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white">
              <option value="">any</option>
              {["defi", "l1", "monetary", "meme", "stablecoin"].map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">Min tier
            <select value={fTier} onChange={(e) => setFTier(e.target.value)}
              className="rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white">
              <option value="">any</option>{["A", "B", "C", "D"].map((t) => <option key={t} value={t}>{t}+</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">Min real yield %
            <input value={fYield} onChange={(e) => setFYield(e.target.value)} placeholder="e.g. 4.5"
              className="w-24 rounded-lg border border-edge bg-panel2 px-2 py-1.5 text-sm text-white" />
          </label>
          <label className="flex items-center gap-2 pb-1.5 text-xs text-muted">
            <input type="checkbox" checked={fNoFlags} onChange={(e) => setFNoFlags(e.target.checked)} /> no gate flags
          </label>
          <button onClick={applyFilter} className="btn">Filter</button>
          {filtered && <button onClick={() => setFiltered(null)} className="text-xs text-muted hover:text-white">clear</button>}
        </div>
        {filtered && (
          <div>
            <div className="mb-2 text-xs text-muted">{filtered.rows.length} of {filtered.universe} tokens match</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted">
                  <tr className="border-b border-edge"><th className="p-2">Token</th><th className="p-2">Class</th><th className="p-2 w-40">Score</th><th className="p-2">Tier</th><th className="p-2">Conf</th></tr>
                </thead>
                <tbody>
                  {filtered.rows.map((r) => (
                    <tr key={r.token} className="border-b border-edge/60">
                      <td className="p-2 font-medium"><TokenLink token={r.token} /></td>
                      <td className="p-2 text-muted">{r.class ?? "—"}</td>
                      <td className="p-2"><div className="flex items-center gap-2"><ScoreBar value={r.score} /><span className="w-12 text-right tabular-nums">{fmt(r.score)}</span></div></td>
                      <td className="p-2"><TierBadge tier={r.tier} /></td>
                      <td className="p-2 text-xs text-muted">{r.confidence}</td>
                    </tr>
                  ))}
                  {filtered.rows.length === 0 && <tr><td colSpan={5} className="p-3 text-center text-muted">No matches.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {!rows && !error && <div className="card"><Spinner /></div>}
      {error && <div className="card border-rose-500/30 text-rose-200">{error}</div>}
      {rows && rows.length === 0 && (
        <div className="card text-muted">
          No saved universe yet. Click <b>Build / refresh search</b> above, or run{" "}
          <code>dyor collect --top-n 50 --persist</code>.
        </div>
      )}

      {rows && rows.length > 0 && (
        <>
          {/* tier tabs */}
          <div className="flex flex-wrap gap-2">
            {TIERS.map(([letter, name]) => (
              <button key={letter} onClick={() => setActiveTier(letter)}
                className={`rounded-lg border px-3 py-1.5 text-sm ${
                  activeTier === letter ? "border-brand bg-panel2 text-white" : "border-edge text-muted hover:text-white"
                }`}>
                <span className="font-semibold">Tier {letter}</span>
                <span className="ml-1 text-xs text-muted">{name}</span>
                <span className="ml-2 rounded-full bg-edge px-1.5 text-xs">{byTier[letter].length}</span>
              </button>
            ))}
          </div>

          <TierTable rows={active} total={byTier[activeTier].length} />
        </>
      )}
    </div>
  );
}

function TierTable({ rows, total }: { rows: Score[]; total: number }) {
  if (rows.length === 0) {
    return <div className="card text-muted">No tokens in this tier.</div>;
  }
  return (
    <div className="card !p-0 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase text-muted">
          <tr className="border-b border-edge">
            <th className="p-3 w-8">#</th>
            <th className="p-3">Token</th>
            <th className="p-3">Class</th>
            <th className="p-3 w-48">Final</th>
            <th className="p-3">Tier</th>
            <th className="p-3">Coverage</th>
            <th className="p-3">Flags</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.token} className="border-b border-edge/60 hover:bg-panel2/40">
              <td className="p-3 text-muted">{i + 1}</td>
              <td className="p-3 font-medium"><TokenLink token={r.token} /></td>
              <td className="p-3 text-muted">{r.class?.label ?? "—"}</td>
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <ScoreBar value={r.final_score} />
                  <span className="w-12 text-right tabular-nums">{fmt(r.final_score)}</span>
                </div>
              </td>
              <td className="p-3"><TierBadge tier={r.tier} /></td>
              <td className="p-3 tabular-nums text-muted">{r.coverage === null ? "—" : `${Math.round(r.coverage * 100)}%`}</td>
              <td className="p-3 text-xs text-rose-300">{r.flags.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {total > rows.length && (
        <div className="border-t border-edge p-2 text-center text-xs text-muted">
          showing top {rows.length} of {total}
        </div>
      )}
    </div>
  );
}

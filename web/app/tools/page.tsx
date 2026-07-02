"use client";
import { useState } from "react";
import { api, type BacktestResult, type BarbellResult, type PortfolioResult } from "@/lib/api";
import { fmt, Spinner, TierBadge } from "@/components/ui";
import TokenLink from "@/components/TokenLink";
import { useStickyState } from "@/components/AppState";

export default function ToolsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">🧪 Tools</h1>
        <p className="mt-1 text-muted">Portfolio scoring, the Barbell builder, and a tier backtest — research aids, not advice.</p>
      </div>
      <PortfolioTool />
      <BarbellTool />
      <BacktestTool />
    </div>
  );
}

function PortfolioTool() {
  const [input, setInput] = useStickyState("tools:pf:input", "bitcoin, ethereum, solana, aave, dogecoin");
  const [res, setRes] = useStickyState<PortfolioResult | null>("tools:pf:res", null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const tokens = input.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean).join(",");
    if (!tokens) return;
    setLoading(true); setError(null); setRes(null);
    try { setRes(await api.portfolio(tokens)); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }

  return (
    <section className="card space-y-3">
      <h2 className="font-semibold text-white">📦 Portfolio scorer</h2>
      <p className="text-sm text-muted">Enter holdings (names/symbols/addresses, comma or newline separated).</p>
      <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={2} className="input" />
      <button onClick={run} disabled={loading} className="btn">{loading ? "Scoring…" : "Score portfolio"}</button>
      {loading && <Spinner label="Analyzing each holding live…" />}
      {error && <div className="text-rose-300">{error}</div>}
      {res && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-4 text-sm">
            <div><span className="text-muted">Avg score</span> <b className="text-white">{fmt(res.avg_score)}</b></div>
            <div><span className="text-muted">Tiers</span> <b className="text-white">{Object.entries(res.tier_distribution).map(([t, n]) => `${t}:${n}`).join(" ") || "—"}</b></div>
            <div><span className="text-muted">Classes</span> <b className="text-white">{Object.entries(res.class_exposure).map(([c, n]) => `${c}:${n}`).join(" ") || "—"}</b></div>
          </div>
          {res.notes.map((n) => <div key={n} className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-sm text-amber-200">⚠ {n}</div>)}
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted"><tr className="border-b border-edge"><th className="p-2">Holding</th><th className="p-2">Class</th><th className="p-2">Score</th><th className="p-2">Tier</th></tr></thead>
            <tbody>
              {res.holdings.map((h, i) => (
                <tr key={i} className="border-b border-edge/60">
                  <td className="p-2 text-white">
                    {h.token ? <TokenLink token={h.token} label={`${h.name ?? h.token}${h.symbol ? ` (${h.symbol})` : ""}`} /> : (h.query ?? "—")}
                  </td>
                  <td className="p-2 text-muted">{h.class ?? (h.error ?? "—")}</td>
                  <td className="p-2 tabular-nums">{h.score == null ? "—" : fmt(h.score)}</td>
                  <td className="p-2">{h.tier ? <TierBadge tier={h.tier} /> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BarbellTool() {
  const [n, setN] = useStickyState("tools:bb:n", 5);
  const [res, setRes] = useStickyState<BarbellResult | null>("tools:bb:res", null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true); setError(null); setRes(null);
    try { setRes(await api.barbell(n)); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }

  return (
    <section className="card space-y-3">
      <h2 className="font-semibold text-white">🏋️ Barbell builder</h2>
      <p className="text-sm text-muted">A BTC monetary anchor + top-N ungated, A/B-tier satellites from the saved universe.</p>
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted">Satellites</span>
        <input type="number" min={1} max={10} value={n} onChange={(e) => setN(Math.max(1, Math.min(10, Number(e.target.value) || 5)))}
          className="w-20 rounded-lg border border-edge bg-panel2 px-2 py-1 text-sm text-white" />
        <button onClick={run} disabled={loading} className="btn">{loading ? "Building…" : "Build barbell"}</button>
      </div>
      {loading && <Spinner />}
      {error && <div className="text-rose-300">{error}</div>}
      {res && (
        <div className="space-y-2">
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            <b className="text-white">⚓ Anchor:</b> <TokenLink token={res.anchor.token} /> — {res.anchor.tier} (score {fmt(res.anchor.score)})
          </div>
          <div className="text-xs uppercase text-muted">Satellites</div>
          {res.satellites.map((s) => (
            <div key={s.token} className="flex items-center justify-between rounded-lg border border-edge bg-panel2 px-3 py-2 text-sm">
              <span><TokenLink token={s.token} /> <span className="text-muted">· {s.class}</span></span>
              <span className="flex items-center gap-2"><TierBadge tier={s.tier} /> <span className="tabular-nums">{fmt(s.score)}</span></span>
            </div>
          ))}
          <p className="text-xs text-muted">{res.rationale}</p>
        </div>
      )}
    </section>
  );
}

function BacktestTool() {
  const [res, setRes] = useStickyState<BacktestResult | null>("tools:bt:res", null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true); setRes(null);
    try { setRes(await api.backtest()); } finally { setLoading(false); }
  }

  return (
    <section className="card space-y-3">
      <h2 className="font-semibold text-white">⏮️ Tier backtest</h2>
      <p className="text-sm text-muted">Per-tier forward return from your persisted runs. Small/noisy until <code>dyor refresh</code> runs accumulate.</p>
      <button onClick={run} disabled={loading} className="btn">{loading ? "Running…" : "Run backtest"}</button>
      {loading && <Spinner />}
      {res && (
        <div className="space-y-2">
          <div className="text-xs text-muted">{res.samples} samples · {res.tokens ?? 0} tokens</div>
          {res.by_tier && Object.keys(res.by_tier).length > 0 ? (
            <table className="w-full max-w-md text-sm">
              <thead className="text-left text-xs uppercase text-muted"><tr className="border-b border-edge"><th className="p-2">Tier</th><th className="p-2">n</th><th className="p-2">Avg return</th><th className="p-2">Win rate</th></tr></thead>
              <tbody>
                {Object.entries(res.by_tier).map(([t, v]) => (
                  <tr key={t} className="border-b border-edge/60">
                    <td className="p-2"><TierBadge tier={t} /></td>
                    <td className="p-2">{v.n}</td>
                    <td className={`p-2 tabular-nums ${v.avg_return >= 0 ? "text-emerald-300" : "text-rose-300"}`}>{(v.avg_return * 100).toFixed(1)}%</td>
                    <td className="p-2 tabular-nums">{(v.win_rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="text-sm text-muted">{res.note}</div>}
        </div>
      )}
    </section>
  );
}

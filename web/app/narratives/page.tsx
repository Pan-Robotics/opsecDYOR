"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtUsd, Spinner } from "@/components/ui";
import { useStickyState } from "@/components/AppState";

const BY: [string, string][] = [
  ["market_cap_change_24h", "24h momentum"],
  ["market_cap", "Market cap"],
  ["volume_24h", "Volume (24h)"],
];

export default function NarrativesPage() {
  const [by, setBy] = useStickyState("narratives:by", "market_cap_change_24h");
  const [rows, setRows] = useStickyState<any[] | null>("narratives:rows", null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(metric: string) {
    setBy(metric);
    setLoading(true);
    setError(null);
    setRows(null);
    try {
      const d = await api.narratives(metric);
      setRows(d.rows);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const max = rows ? Math.max(...rows.map((r) => Math.abs(r.change_24h ?? 0)), 1) : 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">🔥 Narrative rotation</h1>
        <p className="mt-1 max-w-2xl text-muted">
          Capital rotates between narratives (AI, DePIN, RWA, gaming…). Spotting a sector heating
          before price follows is an edge. Ranked live from CoinGecko&apos;s 700+ categories.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {BY.map(([v, l]) => (
          <button key={v} onClick={() => load(v)}
            className={`pill border ${by === v ? "border-brand bg-brand/15 text-white" : "border-edge text-muted hover:text-white"}`}>
            {l}
          </button>
        ))}
        {!rows && !loading && <button onClick={() => load(by)} className="btn ml-auto">Load narratives</button>}
      </div>

      {loading && <div className="card"><Spinner label="Fetching CoinGecko categories…" /></div>}
      {error && <div className="card border-rose-500/30 text-rose-200">{error}</div>}

      {rows && (
        <div className="card !p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted">
              <tr className="border-b border-edge">
                <th className="p-3">Narrative</th>
                <th className="p-3 w-56">24h</th>
                <th className="p-3">Market cap</th>
                <th className="p-3">Volume 24h</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const c = r.change_24h ?? 0;
                return (
                  <tr key={r.name} className="border-b border-edge/60">
                    <td className="p-3 font-medium text-white">{r.name}</td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className="h-2 flex-1 rounded-full bg-edge">
                          <div className={`h-full rounded-full ${c >= 0 ? "bg-emerald-400" : "bg-rose-400"}`}
                               style={{ width: `${(Math.abs(c) / max) * 100}%` }} />
                        </div>
                        <span className={`w-16 text-right tabular-nums ${c >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                          {c > 0 ? "+" : ""}{c.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="p-3 tabular-nums text-muted">{fmtUsd(r.market_cap)}</td>
                    <td className="p-3 tabular-nums text-muted">{fmtUsd(r.volume_24h)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

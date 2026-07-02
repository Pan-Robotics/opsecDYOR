"use client";
import { useEffect, useState } from "react";
import { api, type Methodology } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function MethodologyPage() {
  const [m, setM] = useState<Methodology | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.methodology().then(setM).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="card border-rose-500/30 text-rose-200">{error}</div>;
  if (!m) return <div className="card"><Spinner /></div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">📖 Methodology</h1>
        <p className="mt-1 text-muted">Normalize → weight → gate → tier, asset-class-aware.</p>
      </div>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 font-semibold text-white">Domain weights (default / DeFi)</h3>
          {Object.entries(m.weights).map(([d, w]) => (
            <div key={d} className="flex items-center gap-3 py-1">
              <div className="w-28 capitalize text-muted">{d}</div>
              <div className="h-2 flex-1 rounded-full bg-edge">
                <div className="h-full rounded-full bg-brand" style={{ width: `${w * 100}%` }} />
              </div>
              <div className="w-12 text-right tabular-nums">{Math.round(w * 100)}%</div>
            </div>
          ))}
        </div>
        <div className="card">
          <h3 className="mb-3 font-semibold text-white">Tiers</h3>
          <div className="flex flex-wrap gap-2">
            {m.tiers.map((t) => (
              <span key={t.label} className="pill border border-edge bg-panel2 text-white">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: t.color }} /> {t.label}
              </span>
            ))}
          </div>
          <h3 className="mb-2 mt-5 font-semibold text-white">Hurdle</h3>
          <p className="text-sm text-muted">
            10Y treasury <b className="text-white">{m.reference.treasury_10y_yield_pct}%</b> (as of {m.reference.reference_date}).
            A token paying real yield below it is flagged.
          </p>
        </div>
      </section>

      <section>
        <h3 className="mb-3 font-semibold text-white">Asset classes</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {m.classes.map((c) => (
            <div key={c.name} className="card">
              <div className="font-semibold text-white">{c.label}</div>
              <div className="mt-1 text-sm text-muted">{c.description}</div>
              <div className="mt-2 text-xs text-muted">Judged on: {c.domains.join(", ")}</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="mb-3 font-semibold text-white">Gate — hard disqualifiers</h3>
        <div className="card text-sm text-muted">
          {Object.keys(m.gating).map((g) => (
            <span key={g} className="mr-2 inline-block">• {g.replace(/_/g, " ")}</span>
          ))}
        </div>
      </section>

      <section>
        <h3 className="mb-3 font-semibold text-white">Metric glossary</h3>
        <div className="card !p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted">
              <tr className="border-b border-edge"><th className="p-3">Metric</th><th className="p-3">Good</th><th className="p-3">Meaning</th></tr>
            </thead>
            <tbody>
              {m.glossary.map((g) => (
                <tr key={g.key} className="border-b border-edge/60">
                  <td className="p-3 font-medium text-white">{g.label}</td>
                  <td className="p-3">{g.direction === "lower" ? "↓" : "↑"}</td>
                  <td className="p-3 text-muted">{g.meaning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h3 className="mb-3 font-semibold text-white">🧠 Break your thesis</h3>
        <ul className="card list-disc space-y-1 pl-8 text-sm text-muted">
          {m.break_thesis.map((q) => <li key={q}>{q}</li>)}
        </ul>
      </section>
    </div>
  );
}

import type { Score } from "@/lib/api";

const TIER_COLOR: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  B: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  C: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  D: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

export function tierColor(tier: string) {
  return TIER_COLOR[tier?.trim()?.[0]] ?? "bg-slate-500/15 text-slate-300 border-slate-500/30";
}

export function TierBadge({ tier }: { tier: string }) {
  return <span className={`pill border ${tierColor(tier)}`}>{tier}</span>;
}

export function ClassBadge({ label }: { label: string }) {
  return <span className="pill border border-brand2/30 bg-brand2/15 text-brand2">{label}</span>;
}

export function fmt(n: number | null | undefined, d = 3) {
  return n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(d);
}

export function fmtUsd(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(2)}K`;
  return `$${v.toFixed(2)}`;
}

export function fmtNum(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(2)}K`;
  return v.toLocaleString();
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="card !p-4">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold text-white">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function ScoreBar({ value }: { value: number | null }) {
  const v = value ?? 0;
  const color = v >= 0.8 ? "bg-emerald-400" : v >= 0.6 ? "bg-sky-400" : v >= 0.4 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-edge">
      <div className={`h-full ${color}`} style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }} />
    </div>
  );
}

export function DomainBars({ score }: { score: Score }) {
  const entries = Object.entries(score.domain_scores).filter(([, v]) => v !== null);
  if (!entries.length) return null;
  return (
    <div className="space-y-2">
      {entries.map(([d, v]) => (
        <div key={d} className="flex items-center gap-3">
          <div className="w-28 shrink-0 text-sm capitalize text-muted">{d}</div>
          <div className="flex-1"><ScoreBar value={v} /></div>
          <div className="w-12 text-right text-sm tabular-nums">{fmt(v)}</div>
        </div>
      ))}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-edge border-t-brand" />
      {label ?? "Loading…"}
    </div>
  );
}

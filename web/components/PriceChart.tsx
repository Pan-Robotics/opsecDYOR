"use client";
import { useEffect, useState } from "react";
import { api, type ChartData } from "@/lib/api";
import { Spinner } from "./ui";

const RANGES: [string, number][] = [
  ["1D", 1], ["7D", 7], ["30D", 30], ["90D", 90], ["1Y", 365],
];

const W = 720;
const H = 200;
const PAD = 6;

function Sparkline({ prices, up }: { prices: [number, number][]; up: boolean }) {
  if (prices.length < 2) return null;
  const ys = prices.map((p) => p[1]);
  const min = Math.min(...ys);
  const max = Math.max(...ys);
  const span = max - min || 1;
  const x = (i: number) => PAD + (i / (prices.length - 1)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - ((v - min) / span) * (H - 2 * PAD);
  const line = prices.map((p, i) => `${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  const area = `${PAD},${H - PAD} ${line} ${(W - PAD).toFixed(1)},${H - PAD}`;
  const stroke = up ? "#34d399" : "#fb7185";
  const fill = up ? "#34d39922" : "#fb718522";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-48 w-full" preserveAspectRatio="none">
      <polygon points={area} fill={fill} />
      <polyline points={line} fill="none" stroke={stroke} strokeWidth={1.5}
        vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export default function PriceChart({ id }: { id: string }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<ChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.chart(id, days)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id, days]);

  const up = (data?.change_pct ?? 0) >= 0;
  const last = data?.last;

  return (
    <div className="card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h3 className="font-semibold text-white">Price</h3>
          {last != null && (
            <span className="text-xl font-semibold text-white">
              ${last < 1 ? last.toPrecision(3) : last.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          )}
          {data?.change_pct != null && (
            <span className={up ? "text-sm text-emerald-300" : "text-sm text-rose-300"}>
              {data.change_pct > 0 ? "+" : ""}{data.change_pct}% · {RANGES.find(([, d]) => d === days)?.[0]}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {RANGES.map(([label, d]) => (
            <button key={d} onClick={() => setDays(d)}
              className={`rounded-md px-2 py-1 text-xs ${days === d ? "bg-panel2 text-white" : "text-muted hover:text-white"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-3">
        {loading && <div className="flex h-48 items-center justify-center"><Spinner /></div>}
        {error && <div className="flex h-48 items-center justify-center text-sm text-muted">No price data ({error})</div>}
        {!loading && !error && data && <Sparkline prices={data.prices} up={up} />}
      </div>
    </div>
  );
}

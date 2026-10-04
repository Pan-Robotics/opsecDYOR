"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type Option = { id: string; name: string; symbol: string };

// Pick up to six board tokens by name or symbol; navigates to /compare?tokens=...
export default function ComparePicker({ initial, options }: { initial: string[]; options: Option[] }) {
  const router = useRouter();
  const [ids, setIds] = useState<string[]>(initial);
  const [q, setQ] = useState("");
  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options]);

  const matches = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    return options
      .filter((o) => !ids.includes(o.id) && (`${o.name} ${o.symbol} ${o.id}`.toLowerCase().includes(t)))
      .slice(0, 8);
  }, [q, ids, options]);

  function go(next: string[]) {
    setIds(next);
    router.push(next.length ? `/compare?tokens=${encodeURIComponent(next.join(","))}` : "/compare");
  }

  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {ids.map((id) => {
          const o = byId.get(id);
          return (
            <button key={id} type="button" onClick={() => go(ids.filter((x) => x !== id))}
              className="pill border border-edge bg-panel2 text-white hover:border-rose-400/60" title="remove">
              {o ? `${o.name} (${o.symbol})` : id} x
            </button>
          );
        })}
        {ids.length === 0 && <span className="text-sm text-muted">No tokens selected yet.</span>}
      </div>
      {ids.length < 6 && (
        <div className="relative">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Add a token by name or symbol, e.g. Aave, UNI, Solana"
            className="input" aria-label="Add a token to compare" />
          {matches.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-edge bg-panel shadow-xl">
              {matches.map((o) => (
                <li key={o.id}>
                  <button type="button" onClick={() => { setQ(""); go([...ids, o.id]); }}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-panel2">
                    <span className="text-white">{o.name}</span><span className="text-xs text-muted">{o.symbol}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className="text-xs text-muted">Up to six tokens from the board. A token that is not on the board can be analyzed live from the Analyze page.</p>
    </div>
  );
}

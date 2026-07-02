"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, type Analysis } from "@/lib/api";
import { Spinner } from "@/components/ui";
import TokenReport from "@/components/TokenReport";
import Markdown from "@/components/Markdown";
import { useStickyState } from "@/components/AppState";

export default function AnalyzePage() {
  return (
    <Suspense fallback={<div className="card"><Spinner /></div>}>
      <AnalyzeInner />
    </Suspense>
  );
}

const PEER_MODES: [string, string][] = [
  ["class", "Same asset class (fairest)"],
  ["stored", "Last saved run"],
  ["sample", "Sample set"],
  ["category", "Its category (slower)"],
];

function AnalyzeInner() {
  const [q, setQ] = useStickyState("analyze:q", "");
  const [peerMode, setPeerMode] = useStickyState("analyze:peerMode", "class");
  const [penalize, setPenalize] = useStickyState("analyze:penalize", true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useStickyState<string | null>("analyze:error", null);
  const [result, setResult] = useStickyState<Analysis | null>("analyze:result", null);
  const [memo, setMemo] = useStickyState<string | null>("analyze:memo", null);
  const [memoLoading, setMemoLoading] = useState(false);

  const runQuery = useCallback(async (query: string) => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setMemo(null);
    try {
      setResult(await api.analyze(query.trim(), peerMode, penalize));
    } catch (err: any) {
      setError(err.message ?? "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, [peerMode, penalize]);

  function run(e?: React.FormEvent) {
    e?.preventDefault();
    runQuery(q);
  }

  // Auto-run when arriving with ?q=<token> (from the screener or a peer link),
  // re-running whenever the param changes even if the page is already open.
  const params = useSearchParams();
  const urlQ = params.get("q");
  useEffect(() => {
    if (urlQ && urlQ.trim()) {
      setQ(urlQ);
      runQuery(urlQ);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQ]);

  async function loadMemo() {
    if (!result?.resolved) return;
    setMemoLoading(true);
    try {
      const d = await api.memo(result.resolved.gecko_id, peerMode);
      setMemo(d.memo);
    } catch (err: any) {
      setMemo("Could not generate memo: " + err.message);
    } finally {
      setMemoLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">🔍 Analyze a token</h1>
        <p className="mt-1 text-muted">
          Search by <b className="text-white">name</b> (Aave), <b className="text-white">symbol</b> (UNI),
          or <b className="text-white">contract address</b> — an address resolves the unified token across all its chains.
        </p>
      </div>

      <form onSubmit={run} className="card space-y-3">
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g.  AAVE   ·   Lido DAO   ·   0x514910771AF9Ca656af840dff83E8264EcF986CA"
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Compare against:</span>
          {PEER_MODES.map(([val, label]) => (
            <button
              type="button"
              key={val}
              onClick={() => setPeerMode(val)}
              className={`pill border ${peerMode === val ? "border-brand bg-brand/15 text-white" : "border-edge text-muted hover:text-white"}`}
            >
              {label}
            </button>
          ))}
          <button type="submit" className="btn ml-auto" disabled={loading || !q.trim()}>
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={penalize} onChange={(e) => setPenalize(e.target.checked)} />
          Penalize a missing <span className="text-white">core</span> domain
          <span className="text-muted/70">— e.g. a DeFi app with no fees/revenue is floored, not let off</span>
        </label>
      </form>

      {loading && <div className="card"><Spinner label="Resolving + scoring live…" /></div>}
      {error && (
        <div className="card border-rose-500/30 bg-rose-500/10 text-rose-200">
          Could not analyze <b>{q}</b>: {error}
        </div>
      )}
      {result && result.resolved && (
        <>
          <TokenReport a={result} />
          <div className="card">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold text-white">🧠 Analyst memo</h3>
              {!memo && (
                <button onClick={loadMemo} disabled={memoLoading} className="btn">
                  {memoLoading ? "Writing…" : "Generate memo"}
                </button>
              )}
            </div>
            {memoLoading && <div className="mt-3"><Spinner label="Composing the write-up…" /></div>}
            {memo && <div className="mt-4"><Markdown text={memo} /></div>}
          </div>
        </>
      )}
    </div>
  );
}

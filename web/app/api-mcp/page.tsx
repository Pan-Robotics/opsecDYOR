"use client";
import { useEffect, useState } from "react";
import { api, type OpenApiSchema } from "@/lib/api";
import { Spinner } from "@/components/ui";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8077";
const MCP_URL = process.env.NEXT_PUBLIC_MCP_URL ?? "https://dyor.cryptoopsec.com/mcp";

// ---- REST endpoints (rendered LIVE from /openapi.json) ---------------------
// The table self-updates: add/rename an endpoint or tweak its params/docstring
// and it shows here on next load — no edit to this file needed.
type Endpoint = { method: string; path: string; params: string; desc: string };
type Group = { group: string; rows: Endpoint[] };

// Curated grouping + order for nice UX; any unmapped path falls under "Other"
// so brand-new endpoints still surface automatically.
const GROUP_OF: Record<string, string> = {
  "/api/analyze": "Analyze", "/api/memo": "Analyze",
  "/api/token-record": "Analyze", "/api/chart": "Analyze",
  "/api/screener": "Screener & filter", "/api/screener/build": "Screener & filter",
  "/api/screener/build/{job_id}": "Screener & filter", "/api/screen": "Screener & filter",
  "/api/portfolio": "Portfolio", "/api/barbell": "Portfolio", "/api/backtest": "Portfolio",
  "/api/narratives": "Reference", "/api/classes": "Reference",
  "/api/methodology": "Reference", "/api/benchmark": "Reference", "/api/health": "Reference",
};
const GROUP_ORDER = ["Analyze", "Screener & filter", "Portfolio", "Reference", "Other"];
const HTTP_METHODS = ["get", "post", "put", "patch", "delete"];

function firstLine(s: string): string {
  return (s || "").trim().split("\n")[0].trim();
}

function paramString(op: OpenApiSchema["paths"][string][string]): string {
  return (op.parameters || [])
    .filter((p) => p.in === "query")
    .map((p) => {
      const d = p.schema?.default;
      if (d !== undefined && d !== null && d !== "") return `${p.name}=${d}`;
      return p.required ? p.name : `${p.name}?`;
    })
    .join(", ");
}

function parseOpenApi(schema: OpenApiSchema): Group[] {
  const byGroup: Record<string, Endpoint[]> = {};
  for (const [path, ops] of Object.entries(schema.paths || {})) {
    for (const [method, op] of Object.entries(ops)) {
      if (!HTTP_METHODS.includes(method)) continue;
      const group = GROUP_OF[path] || "Other";
      (byGroup[group] ||= []).push({
        method: method.toUpperCase(),
        path,
        params: paramString(op),
        desc: firstLine(op.description || op.summary || ""),
      });
    }
  }
  return GROUP_ORDER.filter((g) => byGroup[g]?.length).map((g) => ({ group: g, rows: byGroup[g] }));
}

// ---- MCP tools -------------------------------------------------------------
type Tool = { sig: string; desc: string };
const TOOLS: Tool[] = [
  { sig: "analyze_token(query, peer_mode='stored', penalize_missing_core=None)", desc: "Vet ONE token end-to-end: resolve + asset class + 0–1 score & tier + gate flags + per-domain scores + market snapshot + ranked peers." },
  { sig: "resolve_token(query)", desc: "Resolve a name/symbol/contract to a canonical identity (every chain, explorer + project links) WITHOUT scoring — confirm you've got the right token." },
  { sig: "compare_tokens(queries[], peer_mode='stored')", desc: "Analyze several tokens at once → a compact ranked like-for-like summary (token, class, score, tier, coverage, flags)." },
  { sig: "analyst_memo(query, peer_mode='class')", desc: "Reasoned markdown memo: verdict, drivers, risks, and 'break your thesis' answered with the data." },
  { sig: "screen_tokens(asset_class?, min_tier?, min_score?, no_flags?, min_real_yield?, max_fdv_mcap?, limit=25)", desc: "Screen the saved universe by criteria → matching tokens ranked high→low." },
  { sig: "score_portfolio(tokens[], peer_mode='class')", desc: "Score holdings: tier distribution, asset-class exposure, average score, flagged holdings, barbell notes." },
  { sig: "build_barbell(n_satellites=5)", desc: "BTC monetary anchor + the top-N ungated A/B satellites from the saved universe." },
  { sig: "backtest()", desc: "Per-tier average forward return + win-rate from persisted runs." },
  { sig: "narratives(by='market_cap_change_24h', top=20)", desc: "Which crypto sectors are heating up — CoinGecko categories ranked by momentum / market cap / volume." },
  { sig: "asset_classes()", desc: "List the asset classes and what each is judged on, to explain WHY a token scored as it did." },
  { sig: "methodology()", desc: "Weights, tier thresholds, gates, the treasury hurdle, and the metric glossary — to cite the scoring transparently." },
];

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard?.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200); }}
      className="rounded-md border border-edge bg-panel2 px-2 py-1 text-xs text-muted hover:text-white"
    >
      {done ? "copied ✓" : "copy"}
    </button>
  );
}

function Code({ children, label }: { children: string; label?: string }) {
  return (
    <div className="relative">
      {label && <div className="mb-1 text-xs uppercase tracking-wide text-muted">{label}</div>}
      <div className="group relative">
        <pre className="overflow-x-auto rounded-lg border border-edge bg-[#0b0e14] p-3 text-xs leading-relaxed text-sky-100">
          <code>{children}</code>
        </pre>
        <div className="absolute right-2 top-2 opacity-0 transition group-hover:opacity-100">
          <CopyButton text={children} />
        </div>
      </div>
    </div>
  );
}

function MethodPill({ m }: { m: string }) {
  const cls = m === "GET" ? "text-emerald-300 border-emerald-500/30 bg-emerald-500/10"
    : "text-amber-300 border-amber-500/30 bg-amber-500/10";
  return <span className={`pill border ${cls} font-mono text-[11px]`}>{m}</span>;
}

export default function ApiMcpPage() {
  const [health, setHealth] = useState<"checking" | "online" | "offline">("checking");
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [restErr, setRestErr] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${API}/api/health`, { cache: "no-store" })
      .then((r) => setHealth(r.ok ? "online" : "offline"))
      .catch(() => setHealth("offline"));
    api.openapi()
      .then((s) => setGroups(parseOpenApi(s)))
      .catch((e) => setRestErr(e.message));
  }, []);
  const endpointCount = groups?.reduce((n, g) => n + g.rows.length, 0) ?? 0;

  // Hosted (no install): point a client at the URL.
  const hostedAdd = `claude mcp add --transport http dyor ${MCP_URL}`;
  const hostedConfig = `{
  "mcpServers": {
    "dyor": {
      "command": "npx",
      "args": ["mcp-remote", "${MCP_URL}"]
    }
  }
}`;
  // Self-host (local stdio): run it yourself.
  const localConfig = `{
  "mcpServers": {
    "dyor": {
      "command": "dyor-mcp"
    }
  }
}`;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">🔌 API &amp; MCP</h1>
        <p className="mt-1 max-w-3xl text-muted">
          Everything in DYOR is available programmatically — call the <b className="text-white">REST API</b> from
          any script or frontend, or plug the <b className="text-white">MCP server</b> into an AI agent
          (Claude, etc.) so it can vet tokens as native tools. Same scoring engine behind both.
        </p>
        <p className="mt-2 text-xs text-muted">Research aid, not financial advice.</p>
      </div>

      {/* Two surfaces at a glance */}
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-white">REST API</h3>
            <span className="flex items-center gap-1.5 text-xs">
              <span className={`h-2 w-2 rounded-full ${health === "online" ? "bg-emerald-400" : health === "offline" ? "bg-rose-400" : "bg-amber-400"}`} />
              <span className="text-muted">{health === "checking" ? "checking…" : health}</span>
            </span>
          </div>
          <p className="mt-2 text-sm text-muted">FastAPI · JSON · CORS-open for local dev. For scripts, dashboards, and this web app.</p>
          <div className="mt-3 space-y-1 text-sm">
            <div><span className="text-muted">Base URL</span> <code className="text-sky-300">{API}</code></div>
            <div><span className="text-muted">OpenAPI schema</span>{" "}
              <a href={`${API}/openapi.json`} target="_blank" rel="noreferrer" className="text-brand hover:text-brand2">{API}/openapi.json ↗</a>{" "}
              <span className="text-muted">— the endpoint table below renders from it.</span></div>
          </div>
          <div className="mt-3"><Code label="run it">{`uvicorn dyor.api.app:app --port 8077`}</Code></div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-white">MCP server</h3>
            <span className="pill border border-emerald-500/30 bg-emerald-500/10 text-[11px] text-emerald-300">hosted · 11 tools</span>
          </div>
          <p className="mt-2 text-sm text-muted">A Model-Context-Protocol server named <code className="text-sky-300">dyor</code> — exposes the engine as tools an AI agent can call directly. <span className="text-white">No install: just point your client at the URL.</span></p>
          <div className="mt-3 space-y-1 text-sm">
            <div><span className="text-muted">Endpoint</span>{" "}
              <code className="text-sky-300">{MCP_URL}</code></div>
            <div><span className="text-muted">Transport</span> <code className="text-sky-300">streamable-http</code></div>
          </div>
          <div className="mt-3"><Code label="add it (Claude Code)">{hostedAdd}</Code></div>
        </div>
      </section>

      {/* Connecting an agent */}
      <section className="card">
        <h3 className="mb-1 font-semibold text-white">Connect an AI agent (MCP)</h3>
        <p className="mb-3 text-sm text-muted">
          Point any MCP-capable client at the hosted endpoint — nothing to install — then ask it
          <i> &ldquo;analyze rocket pool&rdquo;</i> or <i> &ldquo;screen for DeFi tokens tier B+ with no flags&rdquo;</i>.
          The agent calls the tools and reasons over the results.
        </p>

        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand">Hosted (recommended)</div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Code label="Claude Code — one line">{hostedAdd}</Code>
          <Code label="Claude Desktop / stdio-only clients (mcp-remote bridge)">{hostedConfig}</Code>
        </div>
        <ul className="mt-3 list-disc space-y-1 pl-4 text-sm text-muted">
          <li>Endpoint: <code className="text-sky-300">{MCP_URL}</code> (streamable-http). Cursor, Claude Desktop &ldquo;Connectors&rdquo;, and other URL-based clients can use it directly.</li>
          <li>Tools resolve tokens cross-chain and collect live data on first call, so the first request can take a few seconds.</li>
          <li>Read-only research surface — no API key required. (Hosted by CryptoOpsec; usage may be rate-limited.)</li>
        </ul>

        <div className="mt-5 mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Or self-host (local stdio)</div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Code label="claude_desktop_config.json">{localConfig}</Code>
          <div className="text-sm text-muted">
            <p className="mb-2">Run the server yourself:</p>
            <ul className="list-disc space-y-1 pl-4">
              <li><code className="text-sky-300">pip install .</code> in the DYOR repo, then <code>dyor-mcp</code> is on PATH (or point <code>command</code> at <code className="text-sky-300">/path/to/.venv/bin/dyor-mcp</code>).</li>
              <li>For your own HTTP host: <code className="text-sky-300">dyor-mcp --transport streamable-http --port 8765</code> → <code className="text-sky-300">http://localhost:8765/mcp</code>.</li>
            </ul>
          </div>
        </div>
      </section>

      {/* REST reference — rendered live from /openapi.json */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold text-white">REST endpoints</h2>
          <span className="text-xs text-muted">
            live from{" "}
            <a href={`${API}/openapi.json`} target="_blank" rel="noreferrer" className="text-brand hover:text-brand2">/openapi.json</a>
            {endpointCount ? ` · ${endpointCount} operations` : ""}
          </span>
        </div>
        {restErr && (
          <div className="card text-sm text-muted">
            Couldn&apos;t load the live schema from <code className="text-sky-300">{API}</code> ({restErr}). Is the API running?
          </div>
        )}
        {!restErr && !groups && <div className="card"><Spinner label="loading schema…" /></div>}
        {groups?.map((g) => (
          <div key={g.group} className="card">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">{g.group}</h3>
            <div className="space-y-2">
              {g.rows.map((e) => (
                <div key={`${e.method} ${e.path}`} className="border-t border-edge pt-2 first:border-0 first:pt-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <MethodPill m={e.method} />
                    <code className="text-sm text-white">{e.path}</code>
                    {e.params && <code className="text-xs text-muted">?{e.params}</code>}
                  </div>
                  {e.desc && <p className="mt-1 text-sm text-muted">{e.desc}</p>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {/* MCP tools */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-white">MCP tools</h2>
        <div className="card">
          <div className="space-y-2">
            {TOOLS.map((t) => (
              <div key={t.sig} className="border-t border-edge pt-2 first:border-0 first:pt-0">
                <code className="text-sm text-brand">{t.sig}</code>
                <p className="mt-1 text-sm text-muted">{t.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Examples */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-white">Usage examples</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <Code label="curl — analyze one token">{`curl "${API}/api/analyze?q=rocket-pool&peer_mode=class"`}</Code>
          <Code label="curl — screen DeFi, tier B+, no flags">{`curl "${API}/api/screen?asset_class=defi&min_tier=B&no_flags=true"`}</Code>
          <Code label="JavaScript (fetch)">{`const r = await fetch(
  "${API}/api/analyze?q=uniswap"
);
const a = await r.json();
console.log(a.score.tier, a.score.final_score);`}</Code>
          <Code label="Agent prompt (MCP)">{`Use DYOR to analyze Lido and
explain why it scored that tier,
then screen for L1s rated B or better.`}</Code>
        </div>
      </section>
    </div>
  );
}

# DYOR MCP server

Make DYOR's scorer callable as **tools** by any MCP-capable AI agent. When a user
asks an agent *"is $TOKEN worth a look?"*, the agent calls DYOR and returns an
opinionated, **asset-class-aware**, **gated** assessment — not scraped raw data.

> Scores are a **research aid, not financial advice.** The server's instructions
> tell the agent to present tiers/flags as analysis, never as buy/sell calls.

## Tools

| Tool | What it does |
|---|---|
| `analyze_token(query, peer_mode?, penalize_missing_core?)` | Resolve a token by **name / symbol / contract address** (cross-chain) → asset class, 0–1 score, tier (A→D), gate flags, advisories, per-domain scores, market snapshot, coverage, feed status, ranked peers. **The flagship.** |
| `resolve_token(query)` | Fast identity resolve (no scoring): gecko_id, all chains + addresses, explorer/project links. Confirm you've got the *right* token. |
| `compare_tokens(queries[])` | Analyze several at once → compact ranked summary. |
| `narratives(by?, top?)` | Sectors/narratives ranked by momentum (CoinGecko categories). |
| `asset_classes()` | The classes and what each is judged on (explain *why* a score is what it is). |
| `methodology()` | Weights, tiers, gates, glossary — to cite/explain the scoring transparently. |
| `analyst_memo(query, peer_mode?)` | A reasoned write-up: verdict, what drove it, risks, "break your thesis" answered with data, confidence caveat. |
| `screen_tokens(asset_class?, min_tier?, min_score?, no_flags?, min_real_yield?, max_fdv_mcap?)` | Filter the saved universe by criteria. |
| `score_portfolio(tokens[])` | Tier/class exposure, avg score, flagged holdings, barbell notes. |
| `build_barbell(n_satellites?)` | BTC anchor + top-N ungated A/B satellites. |
| `backtest()` | Per-tier forward return + win-rate from persisted runs. |

Scores now carry **confidence** (high/medium/low) and **tier_stability** (how
robust the tier is to ±20% weight perturbation). `analyze_token` defaults to
`peer_mode="class"` — scoring against the token's **own asset class** (L1↔L1) for
the fairest read; run `dyor reference` once to populate the class baskets.

`peer_mode`: `stored` (last saved universe) · `sample` (built-in) · `category`
(live top-6 of the token's category — slower, fairest like-for-like).

## Run

```bash
dyor-mcp                                 # stdio — for Claude Desktop / Claude Code
dyor-mcp --transport sse --port 8848     # HTTP/SSE — for remote agents (Manus, etc.)
dyor-mcp --transport streamable-http --port 8848
```

(`dyor-mcp` is installed with the package: `pip install -e .`)

## Register

### Claude Code
```bash
claude mcp add dyor -- dyor-mcp
```

### Claude Desktop
Add to `claude_desktop_config.json` (use the venv's absolute path so it resolves):
```json
{
  "mcpServers": {
    "dyor": {
      "command": "/abs/path/to/DYOR/.venv/bin/dyor-mcp"
    }
  }
}
```

### Cursor / other stdio clients
Point the client at the `dyor-mcp` command (or `python -m dyor.mcp_server`).

### Remote agents (HTTP/SSE)
Run `dyor-mcp --transport sse --port 8848` and give the agent the SSE endpoint
(`http://host:8848/sse`). Lock down network exposure before doing this publicly.

## Notes
- The server calls live free APIs (DefiLlama, CoinGecko, CryptoRank, Ethplorer,
  Santiment, GitHub, Sourcify); `analyze_token` takes a few seconds. Optional keys
  (`DYOR_*`) raise rate limits / unlock social.
- For a richer `stored` peer baseline, run `dyor collect --top-n 50 --persist` (or
  the web app's "Build" button) first.

import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: 'DYOR API and MCP server: token scoring for AI agents and scripts',
  description: "Connect Claude, Cursor or any MCP client to DYOR's hosted MCP server, or call the open REST API: analyze_token, screen_tokens, analyst_memo, score_portfolio, build_barbell, backtest. Scores are 0 to 100 with the full ledger.",
  path: '/api-mcp',
});

export default function ApiMcpLayout({ children }: { children: React.ReactNode }) {
  return children;
}

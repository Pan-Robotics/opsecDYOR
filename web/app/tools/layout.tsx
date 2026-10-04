import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: 'Portfolio scorer, barbell builder and tier backtest',
  description: 'Score a whole crypto portfolio for tier mix, asset-class exposure and flagged risks; build a BTC-anchored barbell of qualified, ungated satellites; backtest whether DYOR tiers predicted forward returns.',
  path: '/tools',
});

export default function ToolsLayout({ children }: { children: React.ReactNode }) {
  return children;
}

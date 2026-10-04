import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta({
  title: 'Crypto narrative rotation — which sectors are heating up',
  description: 'Live ranking of 700+ CoinGecko categories by 24h momentum, market cap and volume — spot capital rotating into AI, DePIN, RWA, gaming or privacy before price follows.',
  path: '/narratives',
});

export default function NarrativesLayout({ children }: { children: React.ReactNode }) {
  return children;
}

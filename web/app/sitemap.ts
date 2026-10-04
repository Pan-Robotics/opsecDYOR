import type { MetadataRoute } from "next";
import { serverApi } from "@/lib/api";
import { SITE } from "@/lib/seo";

// Regenerated hourly: the token list changes with the weekly refresh and
// in-place live refreshes move lastModified.
export const revalidate = 3600;

const STATIC: { path: string; priority: number; changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"] }[] = [
  { path: "/", priority: 1.0, changeFrequency: "weekly" },
  { path: "/analyze", priority: 0.9, changeFrequency: "weekly" },
  { path: "/tokens", priority: 0.9, changeFrequency: "daily" },
  { path: "/screener", priority: 0.8, changeFrequency: "weekly" },
  { path: "/compare", priority: 0.7, changeFrequency: "weekly" },
  { path: "/methodology", priority: 0.8, changeFrequency: "monthly" },
  { path: "/api-mcp", priority: 0.7, changeFrequency: "monthly" },
  { path: "/tools", priority: 0.6, changeFrequency: "monthly" },
  { path: "/narratives", priority: 0.6, changeFrequency: "daily" },
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const entries: MetadataRoute.Sitemap = STATIC.map((s) => ({
    url: `${SITE.url}${s.path}`, lastModified: now, changeFrequency: s.changeFrequency, priority: s.priority,
  }));
  const index = await serverApi.tokens(3600);
  const lastMod = index?.collected_at ? new Date(index.collected_at) : now;
  for (const t of index?.tokens ?? []) {
    entries.push({
      url: `${SITE.url}/token/${encodeURIComponent(t.id)}`,
      lastModified: lastMod,
      changeFrequency: "weekly",
      // majors and qualified tiers first in a crawler's budget
      priority: t.tier?.startsWith("A") || t.tier?.startsWith("B") ? 0.8 : 0.6,
    });
  }
  return entries;
}

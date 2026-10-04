import type { Metadata } from "next";

// One place for the site's identity: URLs, names, default copy, structured data.
// NEXT_PUBLIC_DYOR_URL is the canonical origin of THIS app; NEXT_PUBLIC_SITE_URL
// is the parent CryptoOpsec site it belongs to.
export const SITE = {
  url: (process.env.NEXT_PUBLIC_DYOR_URL ?? "https://dyor.cryptoopsec.com").replace(/\/$/, ""),
  name: "DYOR",
  fullName: "DYOR by CryptoOpsec",
  org: "CryptoOpsec",
  orgUrl: (process.env.NEXT_PUBLIC_SITE_URL ?? "https://cryptoopsec.com").replace(/\/$/, ""),
  twitter: process.env.NEXT_PUBLIC_TWITTER_HANDLE || "@cryptoopseccom", // X / Twitter account for cards + sameAs
  title: "DYOR: Crypto Token Scoring on Fundamentals, Tokenomics and On-chain Data",
  description:
    "DYOR scores crypto tokens 0 to 100 on real revenue, tokenomics, on-chain usage, social and developer activity. Asset-class-aware, gated by hard disqualifiers, built on free open data. Token analyzer, screener, compare view, portfolio tools and a hosted MCP server for AI agents.",
  keywords: [
    "crypto token scoring", "crypto fundamentals", "token analysis", "DYOR crypto", "tokenomics analysis",
    "price to fees crypto", "FDV MCAP ratio", "crypto screener", "DeFi token score", "on-chain analysis",
    "crypto research tool", "MCP server crypto", "CryptoOpsec",
  ],
};

// The site-wide card (app/opengraph-image.tsx). A page that sets its own
// `openGraph` block loses the file-convention image, so pageMeta names it.
export const DEFAULT_OG_IMAGE = {
  url: "/opengraph-image", width: 1200, height: 630,
  alt: "DYOR by CryptoOpsec: crypto token scoring on fundamentals, tokenomics and on-chain data",
};

export const abs = (path: string) => (path.startsWith("http") ? path : `${SITE.url}${path.startsWith("/") ? path : `/${path}`}`);

/** Metadata for a normal page: title (templated), description, canonical, OG + Twitter. */
export function pageMeta(opts: { title: string; description: string; path: string; absoluteTitle?: boolean; noindex?: boolean }): Metadata {
  const { title, description, path } = opts;
  return {
    title: opts.absoluteTitle ? { absolute: title } : title,
    description,
    alternates: { canonical: path },
    openGraph: {
      title: opts.absoluteTitle ? title : `${title} | ${SITE.fullName}`,
      description,
      url: path,
      siteName: SITE.fullName,
      type: "website",
      locale: "en_US",
      images: [DEFAULT_OG_IMAGE],
    },
    twitter: {
      card: "summary_large_image",
      title: opts.absoluteTitle ? title : `${title} | ${SITE.fullName}`,
      description,
      images: [DEFAULT_OG_IMAGE.url],
      ...(SITE.twitter ? { site: SITE.twitter, creator: SITE.twitter } : {}),
    },
    ...(opts.noindex ? { robots: { index: false, follow: true } } : {}),
  };
}

/** Serialize JSON-LD safely for a <script type="application/ld+json"> body. */
export const jsonLd = (data: unknown) => JSON.stringify(data).replace(/</g, "\\u003c");

export function orgJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": `${SITE.orgUrl}/#organization`,
    name: SITE.org,
    url: SITE.orgUrl,
    logo: abs("/icons/logo-256.png"),
    ...(SITE.twitter ? { sameAs: [`https://x.com/${SITE.twitter.replace(/^@/, "")}`] } : {}),
  };
}

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": `${SITE.url}/#website`,
    name: SITE.fullName,
    alternateName: "DYOR",
    url: SITE.url,
    description: SITE.description,
    publisher: { "@id": `${SITE.orgUrl}/#organization` },
    inLanguage: "en",
    potentialAction: {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: `${SITE.url}/analyze?q={search_term_string}` },
      "query-input": "required name=search_term_string",
    },
  };
}

export function appJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE.fullName,
    url: SITE.url,
    applicationCategory: "FinanceApplication",
    operatingSystem: "Web",
    description: SITE.description,
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    featureList: [
      "Asset-class-aware 0 to 100 token score with A to D tier",
      "Hard disqualifier gates (extreme FDV/MCAP, no audit on record, dead token)",
      "Per-feature ledger: raw figures, formula, percentile, weight, points",
      "Tier screener over a weekly-refreshed universe",
      "Portfolio scorer, barbell builder, tier backtest",
      "Hosted MCP server and open REST API",
    ],
    publisher: { "@id": `${SITE.orgUrl}/#organization` },
    isAccessibleForFree: true,
  };
}

export function breadcrumbJsonLd(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem", position: i + 1, name: it.name, item: abs(it.path),
    })),
  };
}

export function faqJsonLd(qa: { q: string; a: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: qa.map(({ q, a }) => ({
      "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a },
    })),
  };
}

/** Trim to a search-snippet-sized description without cutting a word. */
export function snippet(text: string, max = 158): string {
  const t = text.replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max - 1);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), 40))}...`;
}

export const tierLetter = (tier: string | null | undefined) => (tier ?? "").trim().charAt(0) || "?";

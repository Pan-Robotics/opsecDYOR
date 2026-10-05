import "./globals.css";
import type { Metadata, Viewport } from "next";
import Link from "next/link";
import localFont from "next/font/local";
import Nav from "@/components/Nav";
import { AppStateProvider } from "@/components/AppState";
import { SITE, jsonLd, orgJsonLd, websiteJsonLd } from "@/lib/seo";

// Self-hosted variable fonts (latin subsets, SIL OFL — see app/fonts/LICENSE.txt):
// no render-blocking third-party stylesheet, no request to Google from the
// visitor's browser, and a build that needs no network.
const inter = localFont({ src: "./fonts/inter-latin.woff2", weight: "300 700", variable: "--font-inter", display: "swap" });
const orbitron = localFont({ src: "./fonts/orbitron-latin.woff2", weight: "400 900", variable: "--font-orbitron", display: "swap" });
const mono = localFont({ src: "./fonts/jetbrains-mono-latin.woff2", weight: "400 600", variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: SITE.title, template: `%s | ${SITE.fullName}` },
  description: SITE.description,
  applicationName: SITE.name,
  keywords: SITE.keywords,
  authors: [{ name: SITE.org, url: SITE.orgUrl }],
  creator: SITE.org,
  publisher: SITE.org,
  category: "finance",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: SITE.fullName,
    locale: "en_US",
    url: "/",
    title: SITE.title,
    description: SITE.description,
  },
  twitter: {
    card: "summary_large_image",
    title: SITE.title,
    description: SITE.description,
    ...(SITE.twitter ? { site: SITE.twitter, creator: SITE.twitter } : {}),
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1, "max-video-preview": -1 },
  },
  manifest: "/manifest.webmanifest",
  ...(process.env.NEXT_PUBLIC_GSC_VERIFICATION ? { verification: { google: process.env.NEXT_PUBLIC_GSC_VERIFICATION } } : {}),
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#050f19",
  colorScheme: "dark",
};

const FOOTER_LINKS: [string, string][] = [
  ["/analyze", "Analyze a token"],
  ["/tokens", "All scored tokens"],
  ["/screener", "Screener: rank and filter"],
  ["/compare", "Compare tokens"],
  ["/tools", "Portfolio, barbell, backtest"],
  ["/narratives", "Narrative rotation"],
  ["/methodology", "Methodology"],
  ["/api-mcp", "API & MCP"],
  ["/pricing", "Plans and waitlist"],
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${orbitron.variable} ${mono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(orgJsonLd()) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(websiteJsonLd()) }} />
        <AppStateProvider>
          <Nav />
          <main id="main" className="mx-auto max-w-6xl px-4 py-5 sm:py-8">{children}</main>
          <footer className="mx-auto max-w-6xl px-4 py-8 text-xs text-muted sm:py-10">
            <nav aria-label="Footer" className="mb-4 flex flex-wrap gap-x-4 gap-y-2.5">
              {FOOTER_LINKS.map(([href, label]) => (
                <Link key={href} href={href} className="hover:text-white">{label}</Link>
              ))}
            </nav>
            <p>
              DYOR is a{" "}
              <a href={SITE.orgUrl} className="text-brand hover:text-brand2">CryptoOpsec</a>{" "}
              app tool: a free, open-data token scorer. Scores are 0 to 100 and asset-class-aware. Research aid, not investment advice.
            </p>
          </footer>
        </AppStateProvider>
      </body>
    </html>
  );
}

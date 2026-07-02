import "./globals.css";
import type { Metadata } from "next";
import Nav from "@/components/Nav";
import { AppStateProvider } from "@/components/AppState";

export const metadata: Metadata = {
  title: "DYOR — CryptoOpsec",
  description: "Asset-class-aware, flight-to-fundamentals scoring for crypto tokens. A CryptoOpsec app tool.",
};

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://www.cryptoopsec.com";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen font-sans antialiased">
        <AppStateProvider>
          <Nav />
          <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
          <footer className="mx-auto max-w-6xl px-4 py-10 text-xs text-muted">
            DYOR — a{" "}
            <a href={SITE_URL} className="text-brand hover:text-brand2">CryptoOpsec</a>{" "}
            app tool · free/open-data token scorer. Research aid, not investment advice.
          </footer>
        </AppStateProvider>
      </body>
    </html>
  );
}

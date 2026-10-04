"use client";
import { useEffect, useState } from "react";

// Share one token's analysis: the permanent page URL (which carries the score
// card as its preview image), a ready-made post for X, the native share sheet
// where the browser has one, and the one-paragraph summary as plain text.
export default function ShareBar({ url, title, text, summary }: {
  url: string;          // absolute or site-relative; made absolute in the browser
  title: string;        // e.g. "Aave (AAVE) scores 57.2/100 on DYOR"
  text: string;         // short post text (no URL; appended)
  summary?: string | null;
}) {
  const [absUrl, setAbsUrl] = useState(url);
  const [canNative, setCanNative] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    try {
      setAbsUrl(new URL(url, window.location.origin).toString());
      setCanNative(typeof navigator !== "undefined" && typeof navigator.share === "function");
    } catch { /* leave as given */ }
  }, [url]);

  function flash(what: string) {
    setDone(what);
    window.setTimeout(() => setDone(null), 1800);
  }

  async function copy(value: string, what: string) {
    try {
      await navigator.clipboard.writeText(value);
      flash(what);
    } catch {
      window.prompt("Copy this:", value);
    }
  }

  const xHref = `https://x.com/intent/post?${new URLSearchParams({ text: `${text} ${absUrl}` }).toString()}`;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" aria-label="Share this analysis">
      <span className="text-muted">Share:</span>
      <button type="button" onClick={() => copy(absUrl, "Link copied")}
        className="pill border border-edge bg-panel2 text-white hover:border-brand/50">Copy link</button>
      <a href={xHref} target="_blank" rel="noopener noreferrer"
        className="pill border border-edge bg-panel2 text-white hover:border-brand/50">Post on X</a>
      {canNative && (
        <button type="button" onClick={() => navigator.share({ title, text, url: absUrl }).catch(() => undefined)}
          className="pill border border-edge bg-panel2 text-white hover:border-brand/50">Share...</button>
      )}
      {summary && (
        <button type="button" onClick={() => copy(`${summary}\n${absUrl}`, "Summary copied")}
          className="pill border border-edge bg-panel2 text-muted hover:text-white">Copy summary</button>
      )}
      {done && <span className="text-emerald-300" role="status">{done}</span>}
    </div>
  );
}

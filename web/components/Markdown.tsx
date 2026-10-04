import React from "react";

// **bold** and _italic_ (a whole `_..._` span with no inner underscores). Other
// underscores are content — feature names like `price_to_fees` must survive.
function inline(s: string): React.ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*|(?<![\w])_[^_\n]+_(?![\w]))/g).filter(Boolean).map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i} className="text-white">{p.slice(2, -2)}</strong>;
    if (p.length > 2 && p.startsWith("_") && p.endsWith("_")) return <em key={i}>{p.slice(1, -1)}</em>;
    return <span key={i}>{p}</span>;
  });
}

/** Minimal markdown for the analyst memo (headers, bullets, bold). */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      {text.split("\n").map((ln, i) => {
        if (ln.startsWith("# ")) return <h2 key={i} className="mt-2 text-lg font-bold text-white">{inline(ln.slice(2))}</h2>;
        if (ln.startsWith("## ")) return <h3 key={i} className="mt-3 font-semibold text-white">{inline(ln.slice(3))}</h3>;
        if (ln.startsWith("- ")) return <div key={i} className="flex gap-2 text-muted"><span className="text-brand">•</span><span>{inline(ln.slice(2))}</span></div>;
        if (!ln.trim()) return <div key={i} className="h-1.5" />;
        return <p key={i} className="text-muted">{inline(ln)}</p>;
      })}
    </div>
  );
}

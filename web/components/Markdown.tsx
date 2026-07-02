import React from "react";

function inline(s: string): React.ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i} className="text-white">{p.slice(2, -2)}</strong>
      : <span key={i}>{p.replace(/_/g, "")}</span>,
  );
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

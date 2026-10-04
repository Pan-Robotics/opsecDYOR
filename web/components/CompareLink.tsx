"use client";
import Link from "next/link";
import { useStickyValue } from "./AppState";

// Opens the compare page with this token added to whatever is already being
// compared in this tab (up to six), instead of starting over.
export default function CompareLink({ id, className }: { id: string; className?: string }) {
  const current = useStickyValue<string[]>("compare:ids", []);
  const others = current.filter((x) => x !== id);
  const ids = [...others, id].slice(-6);
  const label = others.length
    ? `Add to comparison (${others.length} selected)`
    : "Compare with other tokens";
  return (
    <Link href={`/compare?tokens=${encodeURIComponent(ids.join(","))}`} className={className}>
      {label}
    </Link>
  );
}

import Link from "next/link";

/** A clickable token that opens the Analyze page and auto-runs on it. */
export default function TokenLink({ token, label }: { token: string; label?: string }) {
  return (
    <Link
      href={`/analyze?q=${encodeURIComponent(token)}`}
      className="text-white underline-offset-2 hover:text-brand hover:underline"
      title="Analyze this token"
    >
      {label ?? token}
    </Link>
  );
}

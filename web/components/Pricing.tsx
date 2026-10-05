"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CONTACT_KINDS, isWaitlistTier, joinWaitlist, leaveWaitlist, loginUrl, useAccount, type ContactKind, type WaitlistTier } from "@/lib/account";
import { PAID_TIERS, ROWS, TIERS, tierById, type TierId } from "@/lib/tiers";

// The plans table with the waitlist built in. Nothing is for sale yet: a paid
// column's button records the tier on the person's CryptoOpsec account so it can
// be switched on at launch. Signed-out visitors go through the wallet sign-in
// and come back to the same spot with their draft intact.
//
// Layout: one card per tier up to the lg breakpoint, the comparison table above it.

const DRAFT_KEY = "dyor:waitlist-draft";
type Draft = { tier: WaitlistTier; kind: ContactKind; contact: string; note: string; submit: boolean };

const readDraft = (): Draft | null => {
  try { const d = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "null"); return d && isWaitlistTier(d.tier) ? d : null; } catch { return null; }
};
const writeDraft = (d: Draft | null) => { try { d ? sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d)) : sessionStorage.removeItem(DRAFT_KEY); } catch { /* private mode */ } };

const Check = () => <span className="text-emerald-300" aria-label="Included">✓</span>;
const Cell = ({ v }: { v: string | boolean }) =>
  v === true ? <Check /> : v === false ? <span className="text-muted">No</span> : <span>{v}</span>;

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const day = (s: string) => new Date(s).toLocaleDateString(undefined, { dateStyle: "medium" });

export default function Pricing({ heading = "h2" }: { heading?: "h1" | "h2" }) {
  const { loading, user, setUser } = useAccount();
  const [open, setOpen] = useState<WaitlistTier | null>(null);
  const [kind, setKind] = useState<ContactKind>("email");
  const [contact, setContact] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justJoined, setJustJoined] = useState<WaitlistTier | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const handled = useRef(false);

  const waitlist = user?.waitlist ?? null;

  const openFor = (tier: WaitlistTier) => {
    setError(null); setJustJoined(null);
    if (waitlist && !open) { setKind(waitlist.contact_kind ?? "email"); setContact(waitlist.contact ?? ""); setNote(waitlist.note ?? ""); }
    setOpen(tier);
    setTimeout(() => form.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  };

  const signInThenJoin = (tier: WaitlistTier, submit: boolean) => {
    writeDraft({ tier, kind, contact, note, submit });
    const back = new URL(window.location.href);
    back.searchParams.set("waitlist", tier);
    back.hash = "pricing";
    window.location.assign(loginUrl(back.toString()));
  };

  const submit = async (tier: WaitlistTier, k = kind, c = contact, n = note) => {
    if (!user) { signInThenJoin(tier, true); return; }
    setBusy(true); setError(null);
    const r = await joinWaitlist(tier, k, c, n);
    setBusy(false);
    if ("error" in r) {
      if (r.status === 401) { signInThenJoin(tier, true); return; }
      setError(r.error); return;
    }
    writeDraft(null);
    setUser({ ...user, waitlist: r.waitlist });
    setOpen(null); setJustJoined(tier);
  };

  const leave = async () => {
    if (!user || !waitlist) return;
    if (!window.confirm("Leave the waitlist? Your tier choice is removed; you can join again any time.")) return;
    if (await leaveWaitlist()) { setUser({ ...user, waitlist: null }); setJustJoined(null); }
  };

  // Back from sign-in (or a link straight to a tier): ?waitlist=pro opens the form on
  // that tier, or completes the join the person already asked for before signing in.
  useEffect(() => {
    if (loading || handled.current) return;
    handled.current = true;
    const url = new URL(window.location.href);
    const tier = url.searchParams.get("waitlist");
    if (!isWaitlistTier(tier)) return;
    url.searchParams.delete("waitlist");
    window.history.replaceState(null, "", url.pathname + url.search + (url.hash || "#pricing"));
    const draft = readDraft();
    const k = draft?.tier === tier ? draft.kind : "email";
    const c = draft?.tier === tier ? draft.contact : "";
    const n = draft?.tier === tier ? draft.note : "";
    setKind(k); setContact(c); setNote(n);
    if (user && draft?.submit && draft.tier === tier) { void submit(tier, k, c, n); return; }
    openFor(tier);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  const cta = (id: TierId) => {
    if (id === "free") return <Link href="/analyze" className="btn-ghost w-full">Start free</Link>;
    const tier = id as WaitlistTier;
    const mine = waitlist?.tier === tier;
    const label = mine ? (waitlist?.activated_at ? "Active on your account" : "On the waitlist") : waitlist ? `Switch to ${cap(tier)}` : "Join the waitlist";
    return (
      <button type="button" onClick={() => openFor(tier)} disabled={busy}
        className={mine ? "btn-ghost w-full !border-emerald-500/40 !text-emerald-300" : "btn w-full"}
        aria-pressed={mine}>
        {mine ? "✓ " : ""}{label}
      </button>
    );
  };

  const Heading = heading;

  return (
    <section id="pricing" className="scroll-mt-24">
      <Heading className={heading === "h1" ? "text-2xl font-bold text-white" : "text-sm font-semibold uppercase tracking-wide text-muted"}>
        {heading === "h1" ? "Plans and waitlist" : "Plans"}
      </Heading>
      <p className="mt-1 max-w-3xl text-sm text-muted">
        The score stays free and identical for everyone. Paid tiers buy the pipes and the depth: API keys, the hosted MCP server at
        scale, the Tools page, deeper data and alerts. They are not live yet. Pick the one you want and it is switched on for you at launch.
      </p>

      {/* phones and tablets: a card per tier */}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:hidden">
        {TIERS.map((t) => (
          <div key={t.id} className={`card flex flex-col ${t.id === "pro" ? "border-brand/50" : ""}`}>
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-lg font-semibold text-white">{t.name}</h3>
              <span className="text-sm text-brand">{t.price}</span>
            </div>
            <div className="text-sm text-muted">{t.tagline}</div>
            <div className="mt-1 text-xs text-muted">For: {t.audience}</div>
            <div className="mt-3">{cta(t.id)}</div>
            <ul className="mt-4 space-y-2 text-sm">
              {ROWS.map((r) => (
                <li key={r.label} className="flex items-start justify-between gap-3 border-t border-edge/60 pt-2">
                  <span className="text-muted">{r.label}</span>
                  <span className="shrink-0 text-right text-white"><Cell v={r.values[t.id]} /></span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* desktop: the comparison table */}
      <div className="card !p-0 scroll-x mt-4 hidden lg:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-edge align-top">
              <th className="p-4 text-left text-xs font-semibold uppercase tracking-wide text-muted">What you get</th>
              {TIERS.map((t) => (
                <th key={t.id} className={`w-[19%] p-4 text-left ${t.id === "pro" ? "bg-brand/5" : ""}`}>
                  <div className="text-lg font-semibold text-white">{t.name}</div>
                  <div className="text-sm font-normal text-brand">{t.price}</div>
                  <div className="mt-1 text-xs font-normal text-muted">{t.tagline}</div>
                  <div className="mt-3 font-normal">{cta(t.id)}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.label} className="border-b border-edge/60">
                <td className="p-4">
                  <div className="font-medium text-white">{r.label}</div>
                  {r.hint && <div className="text-xs text-muted">{r.hint}</div>}
                </td>
                {TIERS.map((t) => (
                  <td key={t.id} className={`p-4 align-top ${t.id === "pro" ? "bg-brand/5" : ""}`}><Cell v={r.values[t.id]} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-muted">
        Planned allowances; they may change before launch. Everything on DYOR is free until the tiers launch, and joining the
        waitlist costs nothing and commits you to nothing. Your choice is noted on your CryptoOpsec account so the plan can be
        switched on at launch; nothing is charged until you decide to pay.
      </p>

      {/* status: on the waitlist, or just joined */}
      {waitlist && !open && (
        <div className="card mt-4 border-emerald-500/30 bg-emerald-500/5 text-sm">
          <div className="text-white">
            {waitlist.activated_at
              ? `Your ${cap(waitlist.tier)} plan is active on your account.`
              : `You are on the ${cap(waitlist.tier)} waitlist since ${day(waitlist.created_at)}.`}
            {justJoined && !waitlist.activated_at && <span className="ml-1 text-emerald-300">Noted, thank you.</span>}
          </div>
          <div className="mt-1 text-muted">
            {waitlist.contact ? `The launch notice goes ${CONTACT_KINDS.find((k) => k.id === waitlist.contact_kind)?.via ?? "to"} ${waitlist.contact}. ` : "No contact given; you will see it here and on your account page. "}
            {!waitlist.activated_at && "The plan is switched on for this account at launch."}
          </div>
          {!waitlist.activated_at && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="btn-ghost" onClick={() => openFor(waitlist.tier)}>Change</button>
              <button type="button" className="btn-ghost !text-rose-300" onClick={leave}>Leave the waitlist</button>
            </div>
          )}
        </div>
      )}

      {/* the form */}
      {open && (
        <form ref={form} className="card mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); void submit(open); }}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-semibold text-white">{waitlist ? "Change your request" : `Join the ${cap(open)} waitlist`}</h3>
            <span className="text-xs text-muted">{tierById(open)?.tagline}</span>
          </div>
          <label className="block text-sm text-muted">
            Tier
            <select className="select mt-1 w-full sm:w-full" value={open} onChange={(e) => setOpen(e.target.value as WaitlistTier)}>
              {PAID_TIERS.map((t) => <option key={t.id} value={t.id}>{t.name}, {t.price.toLowerCase()}: {t.tagline.toLowerCase()}</option>)}
            </select>
          </label>
          <div className="text-sm text-muted">
            <div>Where to send the launch notice (optional)</div>
            <div className="mt-1 grid gap-2 sm:grid-cols-[11rem_1fr]">
              <select className="select w-full sm:w-full" aria-label="Channel" value={kind} onChange={(e) => setKind(e.target.value as ContactKind)}>
                {CONTACT_KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
              </select>
              <input className="input" aria-label="Address or handle" value={contact} onChange={(e) => setContact(e.target.value)} maxLength={120}
                placeholder={CONTACT_KINDS.find((k) => k.id === kind)?.placeholder} autoComplete="off" spellCheck={false}
                inputMode={kind === "email" ? "email" : "text"} />
            </div>
          </div>
          <label className="block text-sm text-muted">
            What would you use it for? (optional, lets us know what else we should build for you)
            <textarea className="input mt-1 min-h-[4.5rem]" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={3} />
          </label>
          {!user && !loading && (
            <p className="text-xs text-muted">You will sign in with a wallet first (a signature, no transaction, no email) and land back here.</p>
          )}
          {error && <p className="text-sm text-rose-300" role="alert">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn" disabled={busy}>
              {busy ? "Saving..." : user ? (waitlist ? "Save changes" : "Join the waitlist") : "Sign in and join"}
            </button>
            <button type="button" className="btn-ghost" onClick={() => { setOpen(null); setError(null); }}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}

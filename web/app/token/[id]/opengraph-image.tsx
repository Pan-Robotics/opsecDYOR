import { ImageResponse } from "next/og";
import { serverApi } from "@/lib/api";
import { tierLetter } from "@/lib/seo";

export const alt = "DYOR token score card";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const TIER_COLOR: Record<string, string> = { A: "#34d399", B: "#38bdf8", C: "#fbbf24", D: "#fb7185" };
// NOTE: Satori (next/og) rejects NUMERIC children ("more than one child node") — render strings only.
const LABEL: Record<string, string> = {
  fundamental: "Fundamentals", tokenomics: "Tokenomics", onchain: "On-chain", social: "Social", dev: "Developers",
};

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const a = /^[a-z0-9][a-z0-9-]{0,99}$/.test(id) ? await serverApi.token(id) : null;
  const name = a?.resolved?.name ?? id;
  const symbol = a?.resolved?.symbol ?? "";
  const score = a?.score?.final_score ?? null;
  const tier = a?.score?.tier ?? "";
  const letter = tierLetter(tier);
  const color = TIER_COLOR[letter] ?? "#7e96b8";
  const cls = a?.record?.class?.label ?? "";
  const domains = Object.entries(a?.score?.domain_scores ?? {}).filter(([, v]) => v !== null) as [string, number][];
  const weights = a?.record?.class?.weights ?? {};

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", padding: 56,
                    background: "linear-gradient(135deg, #0e1f2f 0%, #050f19 70%)", color: "#e6eaf3", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 44, height: 44, borderRadius: 12, background: "linear-gradient(135deg,#c9a31d,#e3bd44)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26 }}>🧭</div>
            <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 1 }}>DYOR</div>
            <div style={{ fontSize: 22, color: "#7e96b8" }}>by CryptoOpsec</div>
          </div>
          <div style={{ fontSize: 22, color: "#7e96b8" }}>{cls}</div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 44 }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 64, fontWeight: 700, lineHeight: 1.05 }}>{name}</div>
            <div style={{ fontSize: 30, color: "#7e96b8", marginTop: 6 }}>{symbol}</div>
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 24 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
              <div style={{ fontSize: 96, fontWeight: 700, lineHeight: 1 }}>{score === null ? "n/a" : String(score)}</div>
              <div style={{ fontSize: 24, color: "#7e96b8" }}>/ 100</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "14px 22px", borderRadius: 16,
                          border: `3px solid ${color}`, color, background: "rgba(0,0,0,0.25)" }}>
              <div style={{ fontSize: 64, fontWeight: 700, lineHeight: 1 }}>{letter}</div>
              <div style={{ fontSize: 18, marginTop: 4 }}>{/\(([^)]+)\)/.exec(tier)?.[1] ?? "tier"}</div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 40 }}>
          {domains.map(([d, v]) => (
            <div key={d} style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 22 }}>
              <div style={{ width: 190, color: "#7e96b8" }}>{LABEL[d] ?? d}</div>
              <div style={{ flex: 1, height: 14, borderRadius: 7, background: "#24384f", display: "flex" }}>
                <div style={{ width: `${Math.max(0, Math.min(100, v))}%`, height: "100%", borderRadius: 7, background: "#c9a31d" }} />
              </div>
              <div style={{ width: 70, textAlign: "right" }}>{String(Math.round(v))}</div>
              <div style={{ width: 90, textAlign: "right", color: "#7e96b8", fontSize: 18 }}>{weights[d] != null ? `${Math.round(weights[d] * 100)}% wt` : ""}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: "auto", display: "flex", justifyContent: "space-between", fontSize: 20, color: "#7e96b8" }}>
          <div>Scores 0 to 100 vs same-class peers. Open data. Research aid, not advice.</div>
          <div>dyor.cryptoopsec.com</div>
        </div>
      </div>
    ),
    { ...size },
  );
}

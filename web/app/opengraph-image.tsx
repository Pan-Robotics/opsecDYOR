import { ImageResponse } from "next/og";

export const alt = "DYOR by CryptoOpsec: crypto token scoring on fundamentals, tokenomics and on-chain data";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 64,
                    background: "linear-gradient(135deg, #0e1f2f 0%, #050f19 70%)", color: "#e6eaf3", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: "linear-gradient(135deg,#c9a31d,#e3bd44)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32 }}>🧭</div>
          <div style={{ fontSize: 40, fontWeight: 700, letterSpacing: 1 }}>DYOR</div>
          <div style={{ fontSize: 26, color: "#7e96b8" }}>by CryptoOpsec</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ fontSize: 60, fontWeight: 700, lineHeight: 1.1, maxWidth: 1000 }}>
            Qualify any crypto token on the dimensions that actually matter.
          </div>
          <div style={{ fontSize: 28, color: "#7e96b8", maxWidth: 1000, lineHeight: 1.35 }}>
            Fundamentals, tokenomics, on-chain usage, social and developers, scored 0 to 100 against same-class peers, gated by hard disqualifiers, every figure shown.
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 22, color: "#7e96b8" }}>
          <div>Free, open data, API and MCP server for AI agents</div>
          <div>dyor.cryptoopsec.com</div>
        </div>
      </div>
    ),
    { ...size },
  );
}

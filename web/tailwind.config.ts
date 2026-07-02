import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // CryptoOpsec cyber theme (steel-blue darks + gold accent)
        bg: "#050f19",        // cyber-dark
        panel: "#0e1f2f",     // cyber-slate
        panel2: "#192e43",    // cyber-gray
        edge: "#24384f",      // steel border
        brand: "#c9a31d",     // cyber-gold
        brand2: "#e3bd44",    // brighter gold (hover)
        muted: "#7e96b8",     // cyber-steel
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        orbitron: ["Orbitron", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;

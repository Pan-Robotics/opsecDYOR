// Viewport-sized screenshots of every route at phone (390px) and desktop
// (1366px) widths, at several scroll positions, plus the page's sideways
// overflow in px (must be 0). Drives a headless Chrome over the DevTools
// protocol; no Playwright package needed.
//
//   node web/scripts/screenshots.mjs https://dyor.cryptoopsec.com out/            # all routes
//   node web/scripts/screenshots.mjs http://127.0.0.1:3011 out/ "/,/screener" "0,0.5"
//   CHROME=/path/to/chrome node web/scripts/screenshots.mjs ...
// Files: out/<phone|desktop>-<route>-<n>.png
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const BASE = process.argv[2] ?? "https://dyor.cryptoopsec.com";
const OUT = process.argv[3] ?? ".";
const ROUTES = (process.argv[4] ?? "/,/analyze,/screener,/tokens,/compare?tokens=aave,uniswap,lido-dao,/token/aave,/tools,/narratives,/methodology,/api-mcp").split(/,(?=\/)/);
const FRACS = (process.argv[5] ?? "0,0.12,0.3,0.5").split(",").map(Number);
const VIEWS = { phone: { width: 390, height: 844, deviceScaleFactor: 2, mobile: true }, desktop: { width: 1366, height: 900, deviceScaleFactor: 1, mobile: false } };
const CHROME = process.env.CHROME ?? `${process.env.HOME}/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell`;
const PORT = 9335;
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", `--user-data-dir=${mkdtempSync(join(tmpdir(), "dyor-shots-"))}`, "about:blank"], { stdio: "ignore" });
process.on("exit", () => chrome.kill());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let wsUrl; for (let i = 0; i < 50 && !wsUrl; i++) { try { wsUrl = (await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json()).webSocketDebuggerUrl; } catch { await sleep(200); } }
const ws = new WebSocket(wsUrl); await new Promise((r) => (ws.onopen = r));
let seq = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); } };
const send = (method, params = {}, sessionId) => { const id = ++seq; ws.send(JSON.stringify({ id, method, params, sessionId })); return new Promise((res, rej) => pending.set(id, { res, rej })); };
const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
await send("Page.enable", {}, sessionId); await send("Runtime.enable", {}, sessionId);
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId)).result.value;
for (const [name, v] of Object.entries(VIEWS)) {
  await send("Emulation.setDeviceMetricsOverride", v, sessionId);
  await send("Emulation.setTouchEmulationEnabled", { enabled: v.mobile }, sessionId);
  const fracs = v.mobile ? FRACS : FRACS.slice(0, 2);
  for (const route of ROUTES) {
    await send("Page.navigate", { url: BASE + route }, sessionId);
    await sleep(2500);
    for (let i = 0; i < 40; i++) { if (!(await evaluate(`!!document.querySelector(".animate-spin")`))) break; await sleep(250); }
    await sleep(300);
    const total = await evaluate(`document.documentElement.scrollHeight`);
    const overflow = await evaluate(`document.documentElement.scrollWidth - document.documentElement.clientWidth`);
    const slug = route.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home";
    for (const [i, f] of fracs.entries()) {
      await evaluate(`window.scrollTo(0, ${Math.round(f * Math.max(0, total - v.height))})`);
      await sleep(250);
      const { data } = await send("Page.captureScreenshot", { format: "png" }, sessionId);
      writeFileSync(join(OUT, `${name}-${slug}-${i}.png`), Buffer.from(data, "base64"));
    }
    console.log(`${name.padEnd(8)} ${route.padEnd(42)} height ${String(total).padStart(5)} overflow ${overflow}px`);
  }
}
ws.close(); chrome.kill(); process.exit(0);

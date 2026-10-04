// Drives a headless Chrome over the DevTools protocol (no Playwright package
// needed, only a Chrome binary) to check that each tab keeps its state across
// nav clicks and reloads: screener ranking, filters and selection; the compare
// set behind the Compare tab and the token page's "Add to comparison" link;
// the analyze query. Needs a board with at least two tokens.
//
//   node web/scripts/tab-persistence.mjs http://127.0.0.1:3011      # local build
//   node web/scripts/tab-persistence.mjs https://dyor.cryptoopsec.com
//   CHROME=/path/to/chrome node web/scripts/tab-persistence.mjs ...   # other binary
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:3011";
const CHROME = process.env.CHROME ?? `${process.env.HOME}/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell`;
const PORT = 9333;
const profile = mkdtempSync(join(tmpdir(), "dyor-cdp-"));
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, "--headless", "--no-sandbox", "--disable-gpu", "--window-size=1400,1000", `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
process.on("exit", () => chrome.kill());

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function browserWs() {
  for (let i = 0; i < 50; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/json/version`); return (await r.json()).webSocketDebuggerUrl; } catch { await sleep(200); }
  }
  throw new Error("chrome did not start");
}
const ws = new WebSocket(await browserWs());
await new Promise((r) => (ws.onopen = r));
let seq = 0; const pending = new Map();
const pageErrors = [];
ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
  if (m.method === "Runtime.exceptionThrown") pageErrors.push("exception: " + (m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text).split("\n")[0]);
  if (m.method === "Runtime.consoleAPICalled" && (m.params.type === "error" || m.params.type === "warning")) pageErrors.push(m.params.type + ": " + m.params.args.map(a => a.value ?? a.description ?? "").join(" ").slice(0, 200));
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); } };
function send(method, params = {}, sessionId) {
  const id = ++seq; ws.send(JSON.stringify({ id, method, params, sessionId }));
  return new Promise((res, rej) => pending.set(id, { res, rej }));
}
const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
await send("Page.enable", {}, sessionId);
await send("Runtime.enable", {}, sessionId);

async function evaluate(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }, sessionId);
  if (r.exceptionDetails) throw new Error("eval failed: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text) + "\n" + expr);
  return r.result.value;
}
async function goto(path) { await send("Page.navigate", { url: BASE + path }, sessionId); await sleep(800); }
async function waitFor(expr, label, ms = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await evaluate(expr)) return Date.now() - t0; await sleep(100); }
  throw new Error(`timeout waiting for ${label}: ${expr}\npage errors: ${pageErrors.slice(0, 5).join(" | ")}`);
}
const clickText = (sel, text) => evaluate(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(sel)})].find(e => e.textContent.trim() === ${JSON.stringify(text)}); if (!el) return false; el.click(); return true; })()`);
const navTo = async (label, expectPath) => {
  if (!(await clickText("nav[aria-label=Primary] a", label))) throw new Error("no nav link " + label);
  await waitFor(`location.pathname === ${JSON.stringify(expectPath)}`, "nav to " + expectPath);
  await sleep(300);
};
const typeInto = (sel, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);
const detailFetches = () => evaluate(`performance.getEntriesByType("resource").filter(e => e.name.includes("detail=true")).length`);

let failures = 0;
function check(name, ok, detail = "") { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  " + detail : ""}`); if (!ok) failures++; }

// 1. Screener: set a preset, a search, a toggle and two selections.
await goto("/screener");
await waitFor(`document.querySelectorAll("tbody tr").length > 0`, "screener rows");
check("screener loads rows", true, `${await evaluate(`document.querySelectorAll("tbody tr").length`)} rows`);
await clickText("button", "Best real yield");
await typeInto('input[placeholder="name, symbol or id"]', "a");
await evaluate(`[...document.querySelectorAll('input[type=checkbox][aria-label^="compare "]')].slice(0,2).forEach(c => c.click())`);
await sleep(200);
const picked = await evaluate(`[...document.querySelectorAll('input[type=checkbox][aria-label^="compare "]')].filter(c => c.checked).map(c => c.getAttribute("aria-label").slice(8))`);
check("two tokens ticked", picked.length === 2, picked.join(", "));
const fetchesBefore = await detailFetches();

// 2. Away to Compare (empty the first time) and back: everything still there, no refetch.
await navTo("Compare", "/compare");
check("compare tab opens empty the first time", await evaluate(`location.search === ""`));
await navTo("Screener", "/screener");
const backMs = await waitFor(`document.querySelectorAll("tbody tr").length > 0`, "screener rows after return");
check("screener rows back instantly from memory", backMs < 1500 && (await detailFetches()) === fetchesBefore, `${backMs} ms, fetches ${await detailFetches()} (was ${fetchesBefore})`);
check("preset still active", await evaluate(`[...document.querySelectorAll("button")].some(b => b.textContent.trim() === "Best real yield" && b.className.includes("border-brand"))`));
check("rank-by select still real_yield", (await evaluate(`document.querySelector("select").value`)) === "real_yield");
check("search text kept", (await evaluate(`document.querySelector('input[placeholder="name, symbol or id"]').value`)) === "a");
const stillPicked = await evaluate(`[...document.querySelectorAll('input[type=checkbox][aria-label^="compare "]')].filter(c => c.checked).length`);
check("selection kept", stillPicked === 2, `${stillPicked} ticked`);

// 3. Compare selected, then bounce Screener -> Compare: the set is remembered.
await evaluate(`[...document.querySelectorAll("a")].find(a => a.textContent.trim() === "Compare selected").click()`);
await waitFor(`location.pathname === "/compare" && location.search.includes("tokens=")`, "compare with tokens");
const compareUrl = await evaluate(`location.search`);
await waitFor(`document.querySelectorAll("table").length > 0`, "compare table");
await navTo("Screener", "/screener");
await navTo("Compare", "/compare");
check("Compare tab returns to the compared set", (await evaluate(`location.search`)) === compareUrl, await evaluate(`location.search`));
check("picker shows the two chips", (await evaluate(`document.querySelectorAll("button.pill[title=remove]").length`)) === 2);

// 4. Reload: state comes back from sessionStorage.
await evaluate(`location.reload()`); await sleep(2500);
await waitFor(`document.querySelectorAll("table").length > 0`, "compare table after reload");
check("after reload the Compare nav link still carries the set", (await evaluate(`[...document.querySelectorAll("nav[aria-label=Primary] a")].find(a => a.textContent.trim() === "Compare").getAttribute("href")`)).includes("tokens="));
await navTo("Screener", "/screener");
await waitFor(`document.querySelectorAll("tbody tr").length > 0`, "screener rows after reload");
check("screener filters restored after reload", (await evaluate(`document.querySelector("select").value`)) === "real_yield" && (await evaluate(`document.querySelector('input[placeholder="name, symbol or id"]').value`)) === "a");
check("screener selection restored after reload", (await evaluate(`[...document.querySelectorAll('input[type=checkbox][aria-label^="compare "]')].filter(c => c.checked).length`)) === 2);
check("board fetched exactly once after reload", (await detailFetches()) === 1, `${await detailFetches()} fetch(es)`);

// 5. Token page: the compare link adds to the current set rather than replacing it.
const ids = decodeURIComponent(compareUrl.replace("?tokens=", "")).split(",");
await goto(`/token/${ids[0]}`);
await waitFor(`[...document.querySelectorAll("a")].some(a => a.textContent.includes("Add to comparison"))`, "add-to-comparison label");
const href = await evaluate(`[...document.querySelectorAll("a")].find(a => a.textContent.includes("Add to comparison")).getAttribute("href")`);
check("token page link appends to the compared set", href.includes(encodeURIComponent(ids[1])) && href.includes(ids[0]), href);

// 6. Analyze: a typed query survives a tab switch.
await goto("/analyze");
await waitFor(`!!document.querySelector("form input")`, "analyze input");
await typeInto("form input", "lido dao");
await navTo("Screener", "/screener");
await navTo("Analyze", "/analyze");
check("analyze query kept", (await evaluate(`document.querySelector("form input").value`)) === "lido dao");

// 7. Clearing the comparison is remembered too (no stale set comes back).
await navTo("Compare", "/compare");
await waitFor(`document.querySelectorAll("button.pill[title=remove]").length === 2`, "chips");
// remove the chips one at a time, as a person would (each click re-renders the picker)
await evaluate(`document.querySelector("button.pill[title=remove]").click()`);
await waitFor(`document.querySelectorAll("button.pill[title=remove]").length === 1`, "one chip left");
await evaluate(`document.querySelector("button.pill[title=remove]").click()`);
await waitFor(`location.search === ""`, "compare cleared");
await navTo("Screener", "/screener");
await navTo("Compare", "/compare");
check("cleared comparison stays cleared", (await evaluate(`location.search`)) === "");

check("no page exceptions or console errors", pageErrors.length === 0, pageErrors.slice(0, 5).join(" | "));
console.log(failures ? `\n${failures} FAILED` : "\nALL PASSED");
ws.close(); chrome.kill(); process.exit(failures ? 1 : 0);

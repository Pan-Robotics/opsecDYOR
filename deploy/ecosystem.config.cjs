// pm2 process definitions for the DYOR app on the VPS (cryptoopsec.com box).
//
//   pm2 start deploy/ecosystem.config.cjs && pm2 save
//
// Assumes:
//   • repo at /root/DYOR
//   • Python venv at /root/DYOR/.venv with deps installed (pip install .)
//   • web app built:  cd /root/DYOR/web && npm ci && npm run build
//
// DuckDB is single-writer: keep ONE dyor-api instance (no clustering).
module.exports = {
  apps: [
    {
      name: "dyor-api",                 // FastAPI scoring engine on 127.0.0.1:8077
      cwd: "/root/DYOR",
      script: "/root/DYOR/.venv/bin/uvicorn",
      args: "dyor.api.app:app --host 127.0.0.1 --port 8077",
      interpreter: "none",              // it's a venv binary, not a node script
      // DYOR_HOME pins config.yaml / data/ / .cache to the project dir even though
      // the package is pip-installed into site-packages (non-editable).
      env: { PYTHONUNBUFFERED: "1", DYOR_HOME: "/root/DYOR" },
    },
    {
      name: "dyor-web",                 // Next.js UI on 127.0.0.1:3010 (next start)
      cwd: "/root/DYOR/web",
      script: "npm",
      args: "run start",
      env: { NODE_ENV: "production" },
    },
    {
      name: "dyor-mcp",                 // Hosted MCP server on 127.0.0.1:8765 (streamable-http)
      cwd: "/root/DYOR",               // FastMCP binds 127.0.0.1 and serves at /mcp; nginx exposes it
      script: "/root/DYOR/.venv/bin/dyor-mcp",
      args: "--transport streamable-http --port 8765",
      interpreter: "none",
      env: { PYTHONUNBUFFERED: "1", DYOR_HOME: "/root/DYOR" },
    },
  ],
};

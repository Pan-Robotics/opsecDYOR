#!/usr/bin/env bash
# Idempotently add per-IP rate limits to the LIVE dyor vhost.
#
# The live vhost is certbot-managed (it carries the TLS block), so it is never
# overwritten from the repo; this script inserts `limit_req` lines into the
# existing location blocks if they are not already there, validates, reloads.
set -euo pipefail

VHOST="${1:-/etc/nginx/sites-enabled/dyor.cryptoopsec.com}"
ZONES=/etc/nginx/conf.d/dyor-ratelimit.conf
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -f "$VHOST" ] || { echo "vhost not found: $VHOST" >&2; exit 1; }
install -m 0644 "$HERE/nginx-dyor-ratelimit.conf" "$ZONES"

if grep -q "zone=dyor_live" "$VHOST"; then
  echo "rate limits already present in $VHOST"
else
  cp "$VHOST" "$VHOST.bak.$(date +%s)"
  python3 - "$VHOST" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()

# A regex location beats the /api/ prefix, so the live-collection endpoints get
# the tight zone; everything else under /api/ gets the cheap-read zone.
live_block = '''
    # --- live-collection endpoints: tight per-IP limit (see conf.d/dyor-ratelimit.conf) ---
    location ~ ^/api/(analyze|memo|portfolio|screener/build)$ {
        limit_req zone=dyor_live burst=3 nodelay;
        proxy_pass http://127.0.0.1:8077;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
'''
s = s.replace("    location /api/ {\n", live_block + "\n    location /api/ {\n        limit_req zone=dyor_api burst=20 nodelay;\n", 1)
s = s.replace("    location /mcp {\n", "    location /mcp {\n        limit_req zone=dyor_live burst=6 nodelay;\n", 1)
open(p, "w").write(s)
PY
  echo "inserted limit_req into $VHOST"
fi

nginx -t
systemctl reload nginx
echo "nginx reloaded with rate limits"

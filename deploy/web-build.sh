#!/usr/bin/env bash
# Zero-downtime build + restart of the DYOR web app on the VPS.
#
#   /root/DYOR/deploy/web-build.sh
#
# Why: `rm -rf .next && npm run build && pm2 restart` left the running server
# without its build directory for the ~30 s of the build — Googlebot fetched
# the sitemap in exactly that window on 2026-10-04 and Search Console recorded
# "Couldn't fetch". Here the build goes to .next-build while .next keeps
# serving; the swap is two renames and the restart takes about a second.
set -euo pipefail
cd "${DYOR_WEB_DIR:-/root/DYOR/web}"
rm -rf .next-build
NEXT_DIST_DIR=.next-build npm run -s build
# swap: keep the previous build one deploy for a quick rollback
rm -rf .next-prev
[ -d .next ] && mv .next .next-prev
mv .next-build .next
pm2 reload dyor-web --update-env >/dev/null   # cluster mode: new process up before the old one stops
# health: the new build must answer before we call it done
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:3010/ || true)
  [ "$code" = "200" ] && { echo "web build live (HTTP 200)"; exit 0; }
  sleep 1
done
echo "web did not answer 200 after restart — rolling back" >&2
mv .next .next-failed && mv .next-prev .next && pm2 reload dyor-web --update-env >/dev/null
exit 1

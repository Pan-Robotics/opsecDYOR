#!/usr/bin/env bash
# DYOR scheduled refresh — one unit of work: snapshot previous run, collect
# live, persist, alert on changes.
#
# CADENCE (weekly, deliberately): Santiment's free anonymous tier is ~1000
# calls/month and each token costs 2, so a 60-token refresh is 120 calls —
# ~520/month weekly, leaving headroom for the site's on-demand analyses. Daily
# would be ~3600/month and blow the quota; an exhausted quota silently drops
# address_growth/dev_commit_trend, which lowers coverage and shifts scores.
# Daily becomes affordable with a Santiment API key in /root/DYOR/.env.
#
# TOP_N must stay >= the current run size or the screener shrinks: `refresh`
# persists a NEW run and the screener reads only the latest one.
set -uo pipefail

DYOR_DIR=/root/DYOR
TOP_N="${TOP_N:-60}"
LOG=/var/log/dyor-refresh.log
LOCK=/run/dyor-refresh.lock

cd "$DYOR_DIR" || { echo "$(date -Is) FATAL: $DYOR_DIR missing" >>"$LOG"; exit 1; }
exec >>"$LOG" 2>&1

echo "=== $(date -Is) refresh start (top-n=$TOP_N) ==="
start=$(date +%s)

# -n: if a previous run is still going, skip rather than queue two collectors
# fighting over the DuckDB write lock.
# -E 75: distinct exit code when the lock is busy, so "already running" is not
# confused with the CLI's own rc=1 (empty collect) in the log.
flock -n -E 75 "$LOCK" "$DYOR_DIR/.venv/bin/dyor" refresh --top-n "$TOP_N"
rc=$?
elapsed=$(( $(date +%s) - start ))

case $rc in
  0)   echo "=== $(date -Is) refresh OK in ${elapsed}s ===" ;;
  75)  echo "=== $(date -Is) refresh SKIPPED — a previous run is still going ===" ;;
  1)   echo "=== $(date -Is) refresh FAILED — collect returned no records (after ${elapsed}s) ===" ;;
  143) echo "=== $(date -Is) refresh TERMINATED (SIGTERM) after ${elapsed}s ===" ;;
  *)   echo "=== $(date -Is) refresh FAILED rc=$rc after ${elapsed}s ===" ;;
esac
exit $rc

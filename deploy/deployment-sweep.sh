#!/usr/bin/env bash
# DYOR full deployment sweep — source of truth -> code parity -> services ->
# HTTP surface -> data -> scheduling -> behavioural regression.
LOCAL="${DYOR_LOCAL:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
H="${DYOR_SSH_HOST:-cryptoopsec}"
BASE=https://dyor.cryptoopsec.com
pass=0; fail=0; warn=0
ok(){ printf '  \033[32mPASS\033[0m  %-46s %s\n' "$1" "${2:-}"; pass=$((pass+1)); }
no(){ printf '  \033[31mFAIL\033[0m  %-46s %s\n' "$1" "${2:-}"; fail=$((fail+1)); }
wr(){ printf '  \033[33mWARN\033[0m  %-46s %s\n' "$1" "${2:-}"; warn=$((warn+1)); }
sec(){ printf '\n\033[1m%s\033[0m\n' "$1"; }
chk(){ [ "$2" = "$3" ] && ok "$1" "$2" || no "$1" "got=$2 want=$3"; }

cd "$LOCAL" || exit 1

sec "A · SOURCE OF TRUTH (local + GitHub)"
[ -z "$(git status --porcelain)" ] && ok "working tree clean" || wr "working tree clean" "$(git status --porcelain | wc -l) file(s) dirty"
git fetch -q origin 2>/dev/null
L=$(git rev-parse HEAD); R=$(git rev-parse origin/main 2>/dev/null)
[ "$L" = "$R" ] && ok "local HEAD == origin/main" "${L:0:7}" || no "local HEAD == origin/main" "local=${L:0:7} origin=${R:0:7}"
T=$(timeout 600 .venv/bin/python -m pytest -q 2>&1 | tail -1)
echo "$T" | grep -q "failed\|error" && no "local test suite" "$T" || ok "local test suite" "$T"

sec "B · CODE PARITY (server vs local)"
LSUM=$(find dyor -name '*.py' | sort | xargs md5sum | md5sum | cut -d' ' -f1)
RSUM=$(ssh $H "cd /root/DYOR && find dyor -name '*.py' | sort | xargs md5sum | md5sum | cut -d' ' -f1")
chk "dyor/ python tree identical" "$RSUM" "$LSUM"
IMP=$(ssh $H 'cd /tmp && /root/DYOR/.venv/bin/python -c "import dyor;print(dyor.__file__)"')
chk "console scripts import editable tree" "$IMP" "/root/DYOR/dyor/__init__.py"
ssh $H 'ls -d /root/DYOR/.venv/lib/python3.12/site-packages/dyor >/dev/null 2>&1' \
  && no "no stale site-packages copy" "copy still present" || ok "no stale site-packages copy"
F=$(ssh $H 'cd /tmp && /root/DYOR/.venv/bin/python -c "
import inspect, dyor.cli, dyor.reference as r, dyor.ingestion.santiment as s
from dyor.classes import REFERENCE_BASKETS as B
from dyor.metrics.tokenomics import float_ratio
print(int(\"single-writer ACROSS PROCESSES\" in inspect.getsource(dyor.cli._cmd_refresh)),
      int(not hasattr(r,\"_same_class_stored\")), int(hasattr(r,\"_basket_version\")),
      int(hasattr(s.SantimentClient(),\"cache\")), int(\"polkadot\" in s.SLUG_OVERRIDES),
      len(B[\"defi\"]), int(float_ratio(1000.4,1000)==1.0))"')
set -- $F
chk "  fix: refresh releases DB lock" "$1" "1"
chk "  fix: anchor frozen (basket only)" "$2" "1"
chk "  fix: anchor cache versioned" "$3" "1"
chk "  fix: santiment cached" "$4" "1"
chk "  fix: santiment slug overrides" "$5" "1"
chk "  fix: defi basket widened" "$6" "26"
chk "  fix: float_ratio clamped" "$7" "1"

sec "C · SERVICES"
for s in OpsecSite dyor-api dyor-web dyor-mcp; do
  L=$(ssh $H "pm2 jlist" 2>/dev/null | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name']=='$s':
        print(p['pm2_env']['status'], p['pm2_env'].get('restart_time',0)); break
else: print('missing 0')")
  set -- $L
  [ "$1" = "online" ] && ok "pm2 $s" "online, $2 restarts" || no "pm2 $s" "$1"
done
for p in 3000 3010 8077 8765; do
  ssh $H "ss -ltn | grep -q ':$p '" && ok "port $p listening" || no "port $p listening"
done

sec "D · HTTP SURFACE"
for path in / /analyze /screener /narratives /tools /methodology /api-mcp; do
  C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$BASE$path")
  chk "web $path" "$C" "200"
done
for path in /api/health /api/methodology /api/classes /api/narratives "/api/screener?source=stored" /api/benchmark; do
  C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 "$BASE$path")
  chk "api $path" "$C" "200"
done
MCP=$(curl -s --max-time 25 -X POST "$BASE/mcp" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"sweep","version":"0"}}}')
echo "$MCP" | grep -q '"serverInfo"' && ok "mcp initialize" "handshake ok" || no "mcp initialize" "$(echo "$MCP"|head -c 80)"
EXP=$(echo | openssl s_client -servername dyor.cryptoopsec.com -connect dyor.cryptoopsec.com:443 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
DAYS=$(( ($(date -d "$EXP" +%s) - $(date +%s)) / 86400 ))
[ "$DAYS" -gt 20 ] && ok "TLS cert validity" "${DAYS}d left" || wr "TLS cert validity" "${DAYS}d left"
C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 https://cryptoopsec.com/); chk "main site cryptoopsec.com" "$C" "200"
# OpsecSite is a Vite SPA: the Tools card link lives in the JS bundle, not the
# HTML shell, so check the asset the page actually loads.
ASSET=$(curl -s --max-time 25 https://cryptoopsec.com/ | grep -o '/assets/[^"]*\.js' | head -1)
if [ -n "$ASSET" ] && curl -s --max-time 30 "https://cryptoopsec.com$ASSET" | grep -q "dyor.cryptoopsec.com"; then
  ok "main site links to DYOR" "in $ASSET"
else
  no "main site links to DYOR" "not in served bundle"
fi

sec "E · DATA"
D=$(ssh $H 'cd /root/DYOR && .venv/bin/python -c "
from dyor.store import db
con=db.connect()
runs=db.runs(con); latest=db.latest_records(con)
refs=con.execute(\"select count(*), count(distinct asset_class) from reference_records\").fetchone()
print(len(runs), len(latest), refs[0], refs[1])
con.close()"')
set -- $D
ok "persisted runs" "$1"
[ "$2" -ge 60 ] && ok "latest run size" "$2 tokens" || wr "latest run size" "$2 tokens (was 60)"
chk "reference basket rows" "$3" "61"
chk "reference basket classes" "$4" "5"

sec "F · SCHEDULING"
ssh $H 'crontab -l 2>/dev/null | grep -q "dyor-refresh"' && ok "crontab entry" "$(ssh $H 'crontab -l | grep dyor-refresh')" || no "crontab entry"
chk "cron service" "$(ssh $H 'systemctl is-active cron')" "active"
chk "cron enabled at boot" "$(ssh $H 'systemctl is-enabled cron')" "enabled"
ssh $H '[ -x /usr/local/bin/dyor-refresh ]' && ok "wrapper executable" || no "wrapper executable"
ssh $H '[ -f /etc/logrotate.d/dyor-refresh ]' && ok "logrotate config" || no "logrotate config"
ssh $H 'logrotate -d /etc/logrotate.d/dyor-refresh >/dev/null 2>&1' && ok "logrotate config valid" || no "logrotate config valid"
ssh $H '[ -w /var/log/dyor-refresh.log ]' && ok "log writable" || no "log writable"
# Exercise the guard WITHOUT invoking the wrapper: calling dyor-refresh here
# would start a real ~25-minute collect (and burn ~120 Santiment calls) whenever
# the lock happened to be free. Hold the lock in a throwaway process instead and
# check that a second acquisition is refused with the wrapper's -E code.
R=$(ssh $H 'flock /run/dyor-refresh.lock sleep 4 >/dev/null 2>&1 &
            sleep 1
            flock -n -E 75 /run/dyor-refresh.lock true; echo $?
            wait' 2>/dev/null | head -1)
[ "$R" = "75" ] && ok "flock overlap guard" "second acquisition refused (rc=75)" || no "flock overlap guard" "rc=$R"

sec "G · BEHAVIOURAL REGRESSION (production)"
# Detect an in-flight run via the lock, not pgrep: an ssh'd `pgrep -f "dyor
# refresh"` matches its own `bash -c` command line and always reports a hit.
ssh $H 'flock -n /run/dyor-refresh.lock true' >/dev/null 2>&1 && INFLIGHT=no || INFLIGHT=yes
if [ "$INFLIGHT" = yes ]; then
  C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 "$BASE/api/screener?source=stored")
  chk "screener up DURING live collect" "$C" "200"
  # count only the python collector; flock/bash wrappers (and this very command)
  # also match the pattern, so filter on the executable
  H2=$(ssh $H 'n=0; for P in $(pgrep -f "bin/dyor refresh"); do
        case "$(readlink /proc/$P/exe 2>/dev/null)" in *python*) ;; *) continue ;; esac
        n=$((n + $(ls -l /proc/$P/fd 2>/dev/null | grep -ci duckdb)))
      done; echo $n')
  chk "refresh holds 0 DB locks mid-collect" "$H2" "0"
else
  wr "concurrency check" "no refresh in flight to test against"
fi
A1=$(curl -s --max-time 90 "$BASE/api/analyze?q=bitcoin" | python3 -c "import json,sys;print(json.load(sys.stdin)['score']['final_score'])" 2>/dev/null)
curl -s --max-time 90 "$BASE/api/analyze?q=litecoin" >/dev/null
A2=$(curl -s --max-time 90 "$BASE/api/analyze?q=bitcoin" | python3 -c "import json,sys;print(json.load(sys.stdin)['score']['final_score'])" 2>/dev/null)
[ -n "$A1" ] && [ "$A1" = "$A2" ] && ok "anchor drift regression" "bitcoin $A1 stable across same-class persist" \
  || no "anchor drift regression" "$A1 -> $A2"

sec "RESULT"
printf '  %d passed, %d failed, %d warnings\n' $pass $fail $warn
[ $fail -eq 0 ] && printf '  \033[32mDEPLOYMENT HEALTHY\033[0m\n' || printf '  \033[31m%d CHECK(S) FAILED\033[0m\n' $fail

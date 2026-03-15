#!/bin/bash
# AEGIS SMOKE TEST v4.0
# NOTE: set -e is NOT used (would break FAIL counter)
PASS=0
FAIL=0

check() {
  local desc="$1"
  local cmd="$2"
  local expected="$3"
  local actual
  actual=$(eval "$cmd" 2>/dev/null)
  if echo "$actual" | grep -qE "$expected"; then
    echo "  ✅ $desc"
    PASS=$((PASS+1))
  else
    echo "  ❌ $desc"
    echo "     got:      $actual"
    echo "     expected: $expected"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "╔══════════════════════════════════╗"
echo "║     AEGIS SMOKE TEST v4.0        ║"
echo "╚══════════════════════════════════╝"
echo ""

check "orion-hub health" \
  "curl -s http://localhost:8001/health | python3 -c \"import sys,json; print(json.load(sys.stdin)['status'])\"" \
  "operational"

check "openmct-ui HTTP 200" \
  "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080" \
  "200"

check "herald-voice health" \
  "curl -s http://localhost:8002/health | python3 -c \"import sys,json; print(json.load(sys.stdin)['status'])\"" \
  "operational"

check "herald-voice cache populated" \
  "curl -s http://localhost:8002/health | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if d['cache_files']>=9 else d['cache_files'])\"" \
  "ok"

check "WebSocket connection" \
  "python3 -c \"
import asyncio,websockets,json
async def t():
    async with websockets.connect('ws://localhost:8001/ws') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=10)
        print(json.loads(msg)['type'])
asyncio.run(t())
\"" \
  "SYSTEM"

check "event ingestion" \
  "curl -s -X POST http://localhost:8001/api/internal/event \
    -H 'Content-Type: application/json' \
    -d '{\"id\":\"smoke-test-'$(date +%s)'\",\"type\":\"SYSTEM\",\"severity\":\"INFO\",
         \"source\":\"smoke\",\"env\":\"ALL\",\"title\":\"SMOKE TEST\",
         \"body\":\"\",\"timestamp\":\"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'\",
         \"speak\":false,\"metadata\":{}}' \
   | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if d.get('id') else 'fail')\"" \
  "ok"

check "events retrievable" \
  "curl -s 'http://localhost:8001/api/events?limit=5' | python3 -c \"import sys,json; print(len(json.load(sys.stdin)))\"" \
  "[1-9]"

check "AI query responds" \
  "curl -s -X POST http://localhost:8001/api/query \
    -H 'Content-Type: application/json' \
    -d '{\"question\":\"status\",\"env\":\"ALL\"}' \
   | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if len(d.get('answer',''))>5 else 'fail')\"" \
  "ok"

check "status summary has all envs" \
  "curl -s http://localhost:8001/api/status/summary | python3 -c \"
import sys,json; d=json.load(sys.stdin)
expected={'CEDERVALL','VALVX','GWSK','PERSONAL'}
print('ok' if expected.issubset(d.keys()) else 'missing envs')
\"" \
  "ok"

check "webhook accepted" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8001/api/webhook \
    -H 'Content-Type: application/json' \
    -d '{\"alarm\":{\"name\":\"t\",\"sources\":[{\"device\":\"AA\",\"type\":\"include\"}],
         \"triggers\":[{\"key\":\"person\",\"device\":\"AA\"}]},\"timestamp\":1}'" \
  "200"

check "demo-alert script executable" \
  "test -x scripts/demo_alert.sh && echo ok" \
  "ok"

check "demo-presence script executable" \
  "test -x scripts/demo_presence.sh && echo ok" \
  "ok"

check "AEGIS_BUILD_LOG.md exists" \
  "test -f AEGIS_BUILD_LOG.md && echo ok" \
  "ok"

echo ""
echo "══════════════════════════════════"
echo "  RESULT: $PASS passed  |  $FAIL failed"
echo "══════════════════════════════════"

if [ $FAIL -eq 0 ]; then
  echo "  ✅ AEGIS READY FOR CUSTOMER DEMO"
  exit 0
else
  echo "  ❌ AEGIS NOT READY — fix failures above"
  exit 1
fi

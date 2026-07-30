#!/usr/bin/env bash
set -euo pipefail

JAR_PATH="${1:?usage: ci_smoke_test.sh <jar>}"
ROOT="$(pwd)"
SMOKE="$ROOT/smoke"
OUT="$ROOT/out"
PORT="${SERVER_PORT:-25565}"
SERVER_ID="${P_SERVER_UUID:-ci}"

rm -rf "$SMOKE"
mkdir -p "$SMOKE/.zerox" "$OUT"
cp "$JAR_PATH" "$SMOKE/server.jar"
printf 'eula=true\n' > "$SMOKE/eula.txt"
printf 'server-port=%s\nonline-mode=false\nview-distance=2\nsimulation-distance=2\nspawn-protection=0\n' "$PORT" > "$SMOKE/server.properties"
cat > "$SMOKE/.zerox/zerox.properties" <<'EOF'
worker-threads=auto
tnt.max-explosions-per-tick=8
tnt.max-processing-ms-per-tick=5
tnt.log-deferrals=true
EOF

SMOKE="$SMOKE" PORT="$PORT" SERVER_ID="$SERVER_ID" python3 - <<'PY'
import hashlib
import os
from pathlib import Path
root = Path(os.environ['SMOKE']).resolve()
port = os.environ['PORT']
server_id = os.environ['SERVER_ID']
key_hash = 'f584e637e37772eaa684ad6dcfa49858206c02ab68217c69579204600239660b'
fingerprint = hashlib.sha256(f'{server_id}|{port}|{root}'.encode()).hexdigest()
token = hashlib.sha256(f'{fingerprint}|{key_hash}|ZEROX-PAPER-1.21.11'.encode()).hexdigest()
(root / '.zerox/activation.properties').write_text(
    '# ZEROX CI activation\n'
    'format=1\n'
    f'fingerprint={fingerprint}\n'
    f'token={token}\n'
    'activatedAt=ci\n'
)
PY

cd "$SMOKE"
mkfifo console
exec 3<>console
java -Xms1G -Xmx1G -jar server.jar --nogui <console >server.log 2>&1 &
PID=$!

cleanup() {
  if kill -0 "$PID" 2>/dev/null; then
    echo stop >&3 || true
    sleep 2
    kill "$PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

READY=0
for _ in $(seq 1 240); do
  if grep -q 'Done (' server.log && grep -q '\[ZEROX\] Ready in ' server.log; then
    READY=1
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    cat server.log
    wait "$PID" || true
    exit 1
  fi
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  cat server.log
  echo 'Server did not reach the ZEROX ready state' >&2
  exit 1
fi

grep -q 'ZEROX Paper 1.21.11-v2' server.log

echo 'forceload add 0 0' >&3
sleep 3
echo 'fill 0 80 0 15 83 15 minecraft:tnt' >&3
sleep 1
echo 'setblock 0 79 0 minecraft:redstone_block' >&3

PLACED=0
for _ in $(seq 1 15); do
  if grep -q 'Successfully filled 1024 block' server.log; then
    PLACED=1
    break
  fi
  sleep 1
done
if [[ "$PLACED" -ne 1 ]]; then
  cat server.log
  echo 'TNT test volume was not placed' >&2
  exit 1
fi

GUARDED=0
for _ in $(seq 1 120); do
  if grep -q 'TNT load guard deferred' server.log; then
    GUARDED=1
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    cat server.log
    wait "$PID" || true
    exit 1
  fi
  sleep 1
done

if [[ "$GUARDED" -ne 1 ]]; then
  cat server.log
  echo 'TNT guard did not activate' >&2
  exit 1
fi

sleep 15
kill -0 "$PID"
echo tps >&3
sleep 3
echo stop >&3

for _ in $(seq 1 45); do
  if ! kill -0 "$PID" 2>/dev/null; then
    wait "$PID" || true
    trap - EXIT
    cp server.log "$OUT/ci-server.log"
    grep '\[ZEROX\] Ready in ' server.log > "$OUT/ci-startup.txt"
    grep 'TNT load guard deferred' server.log > "$OUT/ci-tnt-guard.txt"
    grep 'TPS from last' server.log | tail -n 1 > "$OUT/ci-tps-after-tnt.txt" || true
    exit 0
  fi
  sleep 1
done

cat server.log
exit 1

#!/usr/bin/env bash
set -euo pipefail

JAR_PATH="${1:?usage: ci_v4_1_migration_test.sh <jar>}"
ROOT="$(pwd)"
SMOKE="$ROOT/smoke-migration"
OUT="$ROOT/out"
PORT="${SERVER_PORT:-25566}"
SERVER_ID="${P_SERVER_UUID:-ci-migration}"

rm -rf "$SMOKE"
mkdir -p "$SMOKE/.zerox" "$SMOKE/config" "$OUT"
cp "$JAR_PATH" "$SMOKE/server.jar"
printf 'eula=true\n' > "$SMOKE/eula.txt"
printf 'server-port=%s\nonline-mode=false\nview-distance=2\nsimulation-distance=2\nspawn-protection=0\n' "$PORT" > "$SMOKE/server.properties"

# Simulate persistent values written by older ZEROX releases.
cat > "$SMOKE/.zerox/zerox.properties" <<'EOF'
worker-threads=auto
behavior.preserve-semantics=true
tnt.load-shedding-enabled=true
tnt.max-explosions-per-tick=4
tnt.max-processing-ms-per-tick=3
tnt.log-deferrals=true
plugins.defer-repeating-tasks=true
plugins.log-overruns=true
plugins.async-core-threads=2
plugins.async-max-threads=4
plugins.async-queue-capacity=4096
EOF
cat > "$SMOKE/spigot.yml" <<'EOF'
settings:
  debug: false
world-settings:
  default:
    max-tnt-per-tick: 16
EOF
cat > "$SMOKE/config/paper-world-defaults.yml" <<'EOF'
_version: 31
entities:
  armor-stands:
    do-collision-entity-lookups: false
misc:
  update-pathfinding-on-block-update: false
environment:
  optimize-explosions: true
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
  echo 'Migration test server did not reach ready state' >&2
  exit 1
fi

grep -q 'ZEROX Paper 1.21.11-v4.1' server.log
grep -q 'Restored legacy v2/v3 gameplay limits' server.log
grep -Eq '^[[:space:]]*max-tnt-per-tick:[[:space:]]*100([[:space:]]|$)' spigot.yml
grep -Eq '^[[:space:]]*do-collision-entity-lookups:[[:space:]]*true([[:space:]]|$)' config/paper-world-defaults.yml
grep -Eq '^[[:space:]]*update-pathfinding-on-block-update:[[:space:]]*true([[:space:]]|$)' config/paper-world-defaults.yml
grep -Eq '^tnt\.load-shedding-enabled=false$' .zerox/zerox.properties
grep -Eq '^plugins\.defer-repeating-tasks=false$' .zerox/zerox.properties
grep -Eq '^migration\.v4-1-gameplay-restored=true$' .zerox/zerox.properties
test -f .zerox/backups/spigot.yml.pre-v4.1.bak
test -f .zerox/backups/config_paper-world-defaults.yml.pre-v4.1.bak

# Deterministically prove a real TNT block primes and completes with no ZEROX fuse deferral.
echo 'forceload add 0 0' >&3
sleep 2
echo 'setblock 8 80 8 minecraft:tnt' >&3
sleep 1
echo 'setblock 8 79 8 minecraft:redstone_block' >&3
sleep 8
echo 'execute unless entity @e[type=minecraft:tnt] unless block 8 80 8 minecraft:tnt run say [ZEROX-CI] TNT-BLASTED' >&3

BLASTED=0
for _ in $(seq 1 30); do
  if grep -q '\[ZEROX-CI\] TNT-BLASTED' server.log; then
    BLASTED=1
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    cat server.log
    wait "$PID" || true
    exit 1
  fi
  sleep 1
done

if [[ "$BLASTED" -ne 1 ]]; then
  cat server.log
  echo 'TNT block did not prime and finish exploding after legacy migration' >&2
  exit 1
fi
if grep -q 'TNT load guard deferred' server.log; then
  cat server.log
  echo 'TNT load shedding remained active after semantic migration' >&2
  exit 1
fi

echo stop >&3
for _ in $(seq 1 45); do
  if ! kill -0 "$PID" 2>/dev/null; then
    wait "$PID" || true
    trap - EXIT
    cp server.log "$OUT/ci-v4-1-migration-server.log"
    grep 'Migrated legacy setting' server.log > "$OUT/ci-v4-1-migrations.txt"
    grep 'Restored legacy v2/v3 gameplay limits' server.log > "$OUT/ci-v4-1-restoration.txt"
    grep '\[ZEROX-CI\] TNT-BLASTED' server.log > "$OUT/ci-v4-1-tnt-blasted.txt"
    grep 'max-tnt-per-tick' spigot.yml | head -n1 > "$OUT/ci-v4-1-tnt-setting.txt"
    exit 0
  fi
  sleep 1
done

cat server.log
exit 1

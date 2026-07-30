#!/usr/bin/env bash
set -euo pipefail

JAR_PATH="${1:?usage: ci_smoke_test.sh <jar>}"
ROOT="$(pwd)"
SMOKE="$ROOT/smoke"
OUT="$ROOT/out"
PORT="${SERVER_PORT:-25565}"
SERVER_ID="${P_SERVER_UUID:-ci}"

rm -rf "$SMOKE" "$ROOT/ci-plugin-src" "$ROOT/ci-plugin-classes"
mkdir -p "$SMOKE/.zerox" "$SMOKE/plugins" "$OUT" "$ROOT/ci-plugin-src/dev/zerox/ci" "$ROOT/ci-plugin-classes"
cp "$JAR_PATH" "$SMOKE/server.jar"
printf 'eula=true\n' > "$SMOKE/eula.txt"
printf 'server-port=%s\nonline-mode=false\nview-distance=2\nsimulation-distance=2\nspawn-protection=0\n' "$PORT" > "$SMOKE/server.properties"
cat > "$SMOKE/.zerox/zerox.properties" <<'EOF'
worker-threads=auto
tnt.max-explosions-per-tick=4
tnt.max-processing-ms-per-tick=3
tnt.log-deferrals=true
plugins.sync-global-budget-ms=6
plugins.sync-per-plugin-budget-ms=3
plugins.sync-task-warning-ms=10
plugins.max-penalty-ticks=20
plugins.defer-repeating-tasks=true
plugins.log-overruns=true
plugins.async-core-threads=2
plugins.async-max-threads=8
plugins.async-queue-capacity=4096
EOF

cat > "$ROOT/ci-plugin-src/dev/zerox/ci/ZeroxLoadGuardCi.java" <<'JAVA'
package dev.zerox.ci;

import java.util.concurrent.atomic.AtomicInteger;
import org.bukkit.plugin.java.JavaPlugin;

public final class ZeroxLoadGuardCi extends JavaPlugin {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger maximum = new AtomicInteger();

    @Override
    public void onEnable() {
        this.getLogger().info("[ZEROX-CI] load-guard plugin enabled");

        this.getServer().getScheduler().runTaskTimer(this, () -> {
            try {
                Thread.sleep(12L);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, 1L, 1L);

        for (int i = 0; i < 32; ++i) {
            this.getServer().getScheduler().runTaskAsynchronously(this, () -> {
                final int now = this.active.incrementAndGet();
                this.maximum.accumulateAndGet(now, Math::max);
                try {
                    Thread.sleep(250L);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    this.active.decrementAndGet();
                }
            });
        }

        this.getServer().getScheduler().runTaskLater(this, () ->
            this.getLogger().info("[ZEROX-CI] async-max=" + this.maximum.get()), 60L);
    }
}
JAVA
cat > "$ROOT/ci-plugin-src/plugin.yml" <<'YAML'
name: ZeroxLoadGuardCi
version: '1.0.0'
main: dev.zerox.ci.ZeroxLoadGuardCi
api-version: '1.21.11'
description: ZEROX scheduler load regression plugin
YAML

API_CLASSES="$ROOT/paper/paper-api/build/classes/java/main"
test -d "$API_CLASSES"
DEPENDENCIES="$(find "$HOME/.gradle/caches/modules-2/files-2.1" -type f -name '*.jar' -print | paste -sd: -)"
javac --release 21 -cp "$API_CLASSES:$DEPENDENCIES" -d "$ROOT/ci-plugin-classes" \
  "$ROOT/ci-plugin-src/dev/zerox/ci/ZeroxLoadGuardCi.java"
cp "$ROOT/ci-plugin-src/plugin.yml" "$ROOT/ci-plugin-classes/plugin.yml"
jar --create --file "$SMOKE/plugins/ZeroxLoadGuardCi.jar" -C "$ROOT/ci-plugin-classes" .

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

grep -q 'ZEROX Paper 1.21.11-v3' server.log
grep -q '\[ZEROX\] Plugin scheduler: sync=6ms global/3ms per plugin; async=2-8 threads, queue=4096.' server.log
grep -q '\[ZEROX-CI\] load-guard plugin enabled' server.log

PLUGIN_GUARD=0
ASYNC_PARALLEL=0
for _ in $(seq 1 60); do
  if grep -q '\[ZEROX\] Main-thread task' server.log && grep -q '\[ZEROX\] Deferred' server.log; then
    PLUGIN_GUARD=1
  fi
  if grep -Eq '\[ZEROX-CI\] async-max=([2-9]|[1-9][0-9]+)' server.log; then
    ASYNC_PARALLEL=1
  fi
  if [[ "$PLUGIN_GUARD" -eq 1 && "$ASYNC_PARALLEL" -eq 1 ]]; then
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    cat server.log
    wait "$PID" || true
    exit 1
  fi
  sleep 1
done

if [[ "$PLUGIN_GUARD" -ne 1 ]]; then
  cat server.log
  echo 'Plugin scheduler guard did not warn and defer the synthetic slow repeating task' >&2
  exit 1
fi
if [[ "$ASYNC_PARALLEL" -ne 1 ]]; then
  cat server.log
  echo 'Bounded async plugin executor did not demonstrate parallel execution' >&2
  exit 1
fi

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
    grep '\[ZEROX\] Plugin scheduler:' server.log > "$OUT/ci-plugin-scheduler.txt"
    grep '\[ZEROX\] Main-thread task' server.log > "$OUT/ci-plugin-slow-task.txt"
    grep '\[ZEROX\] Deferred' server.log > "$OUT/ci-plugin-deferral.txt"
    grep '\[ZEROX-CI\] async-max=' server.log > "$OUT/ci-plugin-async-parallelism.txt"
    grep 'TNT load guard deferred' server.log > "$OUT/ci-tnt-guard.txt"
    grep 'TPS from last' server.log | tail -n 1 > "$OUT/ci-tps-after-tnt.txt" || true
    exit 0
  fi
  sleep 1
done

cat server.log
exit 1

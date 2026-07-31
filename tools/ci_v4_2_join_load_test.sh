#!/usr/bin/env bash
set -euo pipefail

JAR_PATH="${1:?usage: ci_v4_2_join_load_test.sh <jar>}"
ROOT="$(pwd)"
SMOKE="$ROOT/smoke-join-load"
OUT="$ROOT/out"
PORT="${SERVER_PORT:-25567}"
SERVER_ID="${P_SERVER_UUID:-ci-join-load}"

rm -rf "$SMOKE" "$ROOT/ci-v42-src" "$ROOT/ci-v42-classes"
mkdir -p "$SMOKE/.zerox" "$SMOKE/config" "$SMOKE/plugins" "$OUT" \
  "$ROOT/ci-v42-src/dev/zerox/ci" "$ROOT/ci-v42-classes"
cp "$JAR_PATH" "$SMOKE/server.jar"
printf 'eula=true\n' > "$SMOKE/eula.txt"
printf 'server-port=%s\nonline-mode=false\nview-distance=6\nsimulation-distance=4\nspawn-protection=0\n' "$PORT" > "$SMOKE/server.properties"

cat > "$SMOKE/.zerox/zerox.properties" <<'EOF'
worker-threads=auto
behavior.preserve-semantics=true
tnt.load-shedding-enabled=false
plugins.defer-repeating-tasks=false
plugins.async-core-threads=2
plugins.async-max-threads=4
plugins.async-queue-capacity=4096
join.progressive-view-distance=true
join.initial-send-distance=3
join.ramp-interval-ticks=8
join.start-grace-ticks=10
join.max-ramp-steps-per-tick=1
events.listener-warning-ms=15
EOF

# Exact upstream defaults. V4.2 must back up and migrate these before Paper loads them.
cat > "$SMOKE/config/paper-global.yml" <<'EOF'
_version: 31
chunk-loading-basic:
  player-max-chunk-send-rate: 75.0
  player-max-chunk-load-rate: 100.0
  player-max-chunk-generate-rate: -1.0
chunk-loading-advanced:
  auto-config-send-distance: true
  player-max-concurrent-chunk-loads: 0
  player-max-concurrent-chunk-generates: 0
misc:
  max-joins-per-tick: 5
EOF

cat > "$ROOT/ci-v42-src/dev/zerox/ci/ZeroxJoinLoadCi.java" <<'JAVA'
package dev.zerox.ci;

import org.bukkit.event.Event;
import org.bukkit.event.EventHandler;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.plugin.java.JavaPlugin;

public final class ZeroxJoinLoadCi extends JavaPlugin implements Listener {
    @Override
    public void onEnable() {
        this.getServer().getPluginManager().registerEvents(this, this);
        this.getServer().getScheduler().runTaskLater(this, () -> {
            this.getServer().getPluginManager().callEvent(new SlowJoinWorkEvent());
            this.getLogger().info("[ZEROX-CI] SLOW-EVENT-COMPLETED");
        }, 20L);
    }

    @EventHandler
    public void onSlowJoinWork(final SlowJoinWorkEvent event) {
        try {
            Thread.sleep(25L);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    public static final class SlowJoinWorkEvent extends Event {
        private static final HandlerList HANDLERS = new HandlerList();

        @Override
        public HandlerList getHandlers() {
            return HANDLERS;
        }

        public static HandlerList getHandlerList() {
            return HANDLERS;
        }
    }
}
JAVA

cat > "$ROOT/ci-v42-src/plugin.yml" <<'YAML'
name: ZeroxJoinLoadCi
version: '1.0.0'
main: dev.zerox.ci.ZeroxJoinLoadCi
api-version: '1.21.11'
description: ZEROX v4.2 join-load and synchronous event telemetry regression
YAML

API_CLASSES="$ROOT/paper/paper-api/build/classes/java/main"
test -d "$API_CLASSES"
DEPENDENCIES="$(find "$HOME/.gradle/caches/modules-2/files-2.1" -type f -name '*.jar' -print | paste -sd: -)"
javac --release 21 -proc:none -cp "$API_CLASSES:$DEPENDENCIES" -d "$ROOT/ci-v42-classes" \
  "$ROOT/ci-v42-src/dev/zerox/ci/ZeroxJoinLoadCi.java"
cp "$ROOT/ci-v42-src/plugin.yml" "$ROOT/ci-v42-classes/plugin.yml"
jar --create --file "$SMOKE/plugins/ZeroxJoinLoadCi.jar" -C "$ROOT/ci-v42-classes" .

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
  echo 'V4.2 join-load test server did not reach ready state' >&2
  exit 1
fi

grep -q 'ZEROX Paper 1.21.11-v4.2' server.log
grep -q '\[ZEROX\] Join load controller: enabled=true, initial-distance=3, ramp-every=8 ticks, grace=10 ticks, max-steps/tick=1.' server.log
grep -q 'Migrated Paper join/chunk burst defaults' server.log

grep -Eq '^[[:space:]]*player-max-chunk-send-rate:[[:space:]]*35.0([[:space:]]|$)' config/paper-global.yml
grep -Eq '^[[:space:]]*player-max-chunk-load-rate:[[:space:]]*50.0([[:space:]]|$)' config/paper-global.yml
grep -Eq '^[[:space:]]*player-max-chunk-generate-rate:[[:space:]]*12.0([[:space:]]|$)' config/paper-global.yml
grep -Eq '^[[:space:]]*player-max-concurrent-chunk-loads:[[:space:]]*4([[:space:]]|$)' config/paper-global.yml
grep -Eq '^[[:space:]]*player-max-concurrent-chunk-generates:[[:space:]]*2([[:space:]]|$)' config/paper-global.yml
grep -Eq '^[[:space:]]*max-joins-per-tick:[[:space:]]*1([[:space:]]|$)' config/paper-global.yml
test -f .zerox/backups/config_paper-global.yml.pre-v4.2.bak
grep -Eq '^migration\.v4-2-join-load=true$' .zerox/zerox.properties

EVENT_WARNING=0
EVENT_COMPLETED=0
for _ in $(seq 1 90); do
  if grep -q '\[ZEROX\] Main-thread event listener dev.zerox.ci.ZeroxJoinLoadCi for SlowJoinWorkEvent took ' server.log; then
    EVENT_WARNING=1
  fi
  if grep -q '\[ZEROX-CI\] SLOW-EVENT-COMPLETED' server.log; then
    EVENT_COMPLETED=1
  fi
  if [[ "$EVENT_WARNING" -eq 1 && "$EVENT_COMPLETED" -eq 1 ]]; then
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    cat server.log
    wait "$PID" || true
    exit 1
  fi
  sleep 1
done

if [[ "$EVENT_WARNING" -ne 1 ]]; then
  cat server.log
  echo 'Slow synchronous event listener was not attributed' >&2
  exit 1
fi
if [[ "$EVENT_COMPLETED" -ne 1 ]]; then
  cat server.log
  echo 'Synchronous event was skipped or failed to complete' >&2
  exit 1
fi

echo stop >&3
for _ in $(seq 1 45); do
  if ! kill -0 "$PID" 2>/dev/null; then
    wait "$PID" || true
    trap - EXIT
    cp server.log "$OUT/ci-v4-2-join-load-server.log"
    grep 'Join load controller:' server.log > "$OUT/ci-v4-2-join-controller.txt"
    grep 'Migrated Paper join/chunk burst defaults' server.log > "$OUT/ci-v4-2-join-migration.txt"
    grep 'Main-thread event listener dev.zerox.ci.ZeroxJoinLoadCi' server.log > "$OUT/ci-v4-2-event-attribution.txt"
    grep '\[ZEROX-CI\] SLOW-EVENT-COMPLETED' server.log > "$OUT/ci-v4-2-event-completed.txt"
    cp config/paper-global.yml "$OUT/ci-v4-2-paper-global.yml"
    exit 0
  fi
  sleep 1
done

cat server.log
exit 1

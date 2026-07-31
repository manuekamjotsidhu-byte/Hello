#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()


def require(*paths: str) -> Path:
    for path in paths:
        target = root / path
        if target.is_file():
            return target
    raise SystemExit("Required file not found: " + ", ".join(str(root / path) for path in paths))


def replace_once(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch point missing for {description}: {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Reduce the initial per-player chunk burst while retaining Paper's asynchronous
# chunk loading/generation architecture. These are defaults for new installs;
# exact upstream defaults in existing paper-global.yml are migrated below.
global_config = require("paper-server/src/main/java/io/papermc/paper/configuration/GlobalConfiguration.java")
for old, new, description in (
    ("public double playerMaxChunkSendRate = 75.0;", "public double playerMaxChunkSendRate = 35.0; // ZEROX v4.2: smooth join chunk delivery", "chunk send rate"),
    ("public double playerMaxChunkLoadRate = 100.0;", "public double playerMaxChunkLoadRate = 50.0; // ZEROX v4.2: bound per-player async chunk loads", "chunk load rate"),
    ("public double playerMaxChunkGenerateRate = -1.0;", "public double playerMaxChunkGenerateRate = 12.0; // ZEROX v4.2: bound per-player async generation", "chunk generation rate"),
    ("public int playerMaxConcurrentChunkLoads = 0;", "public int playerMaxConcurrentChunkLoads = 4; // ZEROX v4.2: use workers without a join burst", "concurrent chunk loads"),
    ("public int playerMaxConcurrentChunkGenerates = 0;", "public int playerMaxConcurrentChunkGenerates = 2; // ZEROX v4.2: generation parallelism cap", "concurrent chunk generations"),
    ("public int maxJoinsPerTick = 5;", "public int maxJoinsPerTick = 1; // ZEROX v4.2: serialize simultaneous join finalization", "joins per tick"),
):
    replace_once(global_config, old, new, description)

# Tick the progressive view-distance controller once per server tick. It does not
# execute Bukkit/world mutations off-thread; it feeds work gradually into Paper's
# existing asynchronous chunk system.
scheduler = require("paper-server/src/main/java/org/bukkit/craftbukkit/scheduler/CraftScheduler.java")
replace_once(
    scheduler,
    "        ZeroxSchedulerGuard.beginTick(this.currentTick); // ZEROX\n",
    "        ZeroxSchedulerGuard.beginTick(this.currentTick); // ZEROX\n"
    "        io.papermc.paper.zerox.ZeroxJoinLoadController.tick(this.currentTick); // ZEROX v4.2\n",
    "join-load controller heartbeat",
)

# Start the ramp after PlayerJoinEvent has completed, preserving the values that
# plugins observe during the synchronous event. Mark it ready after login packets
# are flushed so chunk expansion begins only after the player is fully connected.
player_list = require(
    "paper-server/src/minecraft/java/net/minecraft/server/players/PlayerList.java",
    "paper-server/src/minecraft/net/minecraft/server/players/PlayerList.java",
)
replace_once(
    player_list,
    "        if (!player.connection.isAcceptingMessages()) {\n            return;\n        }\n\n        final net.kyori.adventure.text.Component jm = playerJoinEvent.joinMessage();\n",
    "        if (!player.connection.isAcceptingMessages()) {\n            return;\n        }\n\n"
    "        io.papermc.paper.zerox.ZeroxJoinLoadController.prepare(player); // ZEROX v4.2\n\n"
    "        final net.kyori.adventure.text.Component jm = playerJoinEvent.joinMessage();\n",
    "join ramp preparation after PlayerJoinEvent",
)
replace_once(
    player_list,
    "        serverGamePacketListenerImpl.resumeFlushing();\n",
    "        serverGamePacketListenerImpl.resumeFlushing();\n"
    "        io.papermc.paper.zerox.ZeroxJoinLoadController.markReady(player); // ZEROX v4.2\n",
    "join ramp activation",
)

# Attribute slow synchronous event handlers to the exact plugin/listener/event.
# They remain synchronous because cancellation and world access are authoritative.
registered_listener = require("paper-api/src/main/java/org/bukkit/plugin/RegisteredListener.java")
replace_once(
    registered_listener,
    "        executor.execute(listener, event);\n",
    "        final long zeroxStarted = System.nanoTime();\n"
    "        try {\n"
    "            executor.execute(listener, event);\n"
    "        } finally {\n"
    "            zeroxRecordEventTime(event, System.nanoTime() - zeroxStarted);\n"
    "        }\n",
    "event listener timing",
)
replace_once(
    registered_listener,
    "    /**\n     * Whether this listener accepts cancelled events\n",
    r'''    private static final long ZEROX_EVENT_WARNING_NANOS = java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(
        Math.max(1, Integer.getInteger("zerox.events.listener-warning-ms", 15))
    );
    private static final java.util.concurrent.ConcurrentHashMap<String, Long> ZEROX_EVENT_WARNINGS = new java.util.concurrent.ConcurrentHashMap<>();

    private void zeroxRecordEventTime(final Event event, final long elapsedNanos) {
        if (event.isAsynchronous() || elapsedNanos < ZEROX_EVENT_WARNING_NANOS) {
            return;
        }
        final String key = this.plugin.getName() + '|' + event.getEventName() + '|' + this.listener.getClass().getName();
        final long now = System.nanoTime();
        final Long previous = ZEROX_EVENT_WARNINGS.put(key, now);
        if (previous != null && now - previous < java.util.concurrent.TimeUnit.SECONDS.toNanos(10)) {
            return;
        }
        this.plugin.getLogger().warning("[ZEROX] Main-thread event listener "
            + this.listener.getClass().getName() + " for " + event.getEventName() + " took "
            + String.format(java.util.Locale.ROOT, "%.2f", elapsedNanos / 1_000_000.0D)
            + "ms. It was not moved off-thread because Bukkit event state and world access must remain authoritative.");
    }

    /**
     * Whether this listener accepts cancelled events
''',
    "slow event listener telemetry",
)

pkg = root / "paper-server/src/main/java/io/papermc/paper/zerox"
pkg.mkdir(parents=True, exist_ok=True)
(pkg / "ZeroxJoinLoadController.java").write_text(r'''package io.papermc.paper.zerox;

import io.papermc.paper.FeatureHooks;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import net.minecraft.server.level.ServerPlayer;

/**
 * Smooths the initial chunk burst for a joining player. All view-distance
 * changes occur on the main thread; Paper's existing chunk system performs
 * eligible loading, generation and I/O on its worker threads.
 */
public final class ZeroxJoinLoadController {
    private static final boolean ENABLED = Boolean.parseBoolean(
        System.getProperty("zerox.join.progressive-view-distance", "true")
    );
    private static final int INITIAL_DISTANCE = intProperty("zerox.join.initial-send-distance", 3, 2, 32);
    private static final int RAMP_INTERVAL_TICKS = intProperty("zerox.join.ramp-interval-ticks", 8, 1, 200);
    private static final int START_GRACE_TICKS = intProperty("zerox.join.start-grace-ticks", 10, 0, 200);
    private static final int MAX_STEPS_PER_TICK = intProperty("zerox.join.max-ramp-steps-per-tick", 1, 1, 64);
    private static final Map<UUID, Ramp> RAMPS = new LinkedHashMap<>();
    private static int currentTick;

    private ZeroxJoinLoadController() {}

    public static void prepare(final ServerPlayer player) {
        if (!ENABLED || player.connection == null || !player.connection.isAcceptingMessages()) {
            return;
        }
        final int targetDistance = player.getBukkitEntity().getSendViewDistance();
        final int initialDistance = Math.min(targetDistance, INITIAL_DISTANCE);
        if (targetDistance <= initialDistance) {
            return;
        }
        FeatureHooks.setSendViewDistance(player, initialDistance);
        RAMPS.put(player.getUUID(), new Ramp(player, initialDistance, targetDistance));
        System.out.println("[ZEROX] Join load smoothing started for " + player.getScoreboardName()
            + ": send-distance " + initialDistance + " -> " + targetDistance
            + ", interval=" + RAMP_INTERVAL_TICKS + " ticks.");
    }

    public static void markReady(final ServerPlayer player) {
        final Ramp ramp = RAMPS.get(player.getUUID());
        if (ramp != null) {
            ramp.ready = true;
            ramp.nextStepTick = currentTick + START_GRACE_TICKS;
        }
    }

    public static void tick(final int tick) {
        currentTick = tick;
        if (!ENABLED || RAMPS.isEmpty()) {
            return;
        }

        int steps = 0;
        final Iterator<Map.Entry<UUID, Ramp>> iterator = RAMPS.entrySet().iterator();
        while (iterator.hasNext()) {
            final Ramp ramp = iterator.next().getValue();
            final ServerPlayer player = ramp.player;
            if (player.connection == null || !player.connection.isAcceptingMessages()) {
                iterator.remove();
                continue;
            }
            if (!ramp.ready || tick < ramp.nextStepTick || steps >= MAX_STEPS_PER_TICK) {
                continue;
            }

            final int observedDistance = player.getBukkitEntity().getSendViewDistance();
            if (observedDistance != ramp.currentDistance) {
                // Respect explicit post-join plugin/admin changes rather than fighting them.
                ramp.currentDistance = observedDistance;
                ramp.targetDistance = observedDistance;
            }

            if (ramp.currentDistance >= ramp.targetDistance) {
                iterator.remove();
                continue;
            }

            final int nextDistance = Math.min(ramp.targetDistance, ramp.currentDistance + 1);
            FeatureHooks.setSendViewDistance(player, nextDistance);
            ramp.currentDistance = nextDistance;
            ramp.nextStepTick = tick + RAMP_INTERVAL_TICKS;
            steps++;

            if (nextDistance >= ramp.targetDistance) {
                iterator.remove();
                System.out.println("[ZEROX] Join load smoothing completed for " + player.getScoreboardName()
                    + " at send-distance " + nextDistance + ".");
            }
        }
    }

    public static void reportConfiguration() {
        System.out.println("[ZEROX] Join load controller: enabled=" + ENABLED
            + ", initial-distance=" + INITIAL_DISTANCE
            + ", ramp-every=" + RAMP_INTERVAL_TICKS + " ticks"
            + ", grace=" + START_GRACE_TICKS + " ticks"
            + ", max-steps/tick=" + MAX_STEPS_PER_TICK + ".");
    }

    private static int intProperty(final String key, final int fallback, final int minimum, final int maximum) {
        try {
            return Math.max(minimum, Math.min(maximum, Integer.parseInt(System.getProperty(key, Integer.toString(fallback)))));
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static final class Ramp {
        private final ServerPlayer player;
        private int currentDistance;
        private int targetDistance;
        private boolean ready;
        private int nextStepTick;

        private Ramp(final ServerPlayer player, final int currentDistance, final int targetDistance) {
            this.player = player;
            this.currentDistance = currentDistance;
            this.targetDistance = targetDistance;
        }
    }
}
''', encoding="utf-8")

bootstrap = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java")
replace_once(
    bootstrap,
    '            settings.setProperty("plugins.async-queue-capacity", "4096");\n',
    '            settings.setProperty("plugins.async-queue-capacity", "4096");\n'
    '            settings.setProperty("join.progressive-view-distance", "true");\n'
    '            settings.setProperty("join.initial-send-distance", "3");\n'
    '            settings.setProperty("join.ramp-interval-ticks", "8");\n'
    '            settings.setProperty("join.start-grace-ticks", "10");\n'
    '            settings.setProperty("join.max-ramp-steps-per-tick", "1");\n'
    '            settings.setProperty("events.listener-warning-ms", "15");\n',
    "join-load defaults",
)
replace_once(
    bootstrap,
    "        migrateLegacyGameplaySettings(settings);\n\n        final int processors = Runtime.getRuntime().availableProcessors();\n",
    "        migrateLegacyGameplaySettings(settings);\n        migrateJoinLoadSettings(settings);\n\n        final int processors = Runtime.getRuntime().availableProcessors();\n",
    "join-load migration invocation",
)
replace_once(
    bootstrap,
    '        setDefaultSystemProperty("zerox.plugins.async-queue-capacity", settings.getProperty("plugins.async-queue-capacity", "4096"));\n',
    '        setDefaultSystemProperty("zerox.plugins.async-queue-capacity", settings.getProperty("plugins.async-queue-capacity", "4096"));\n'
    '        setDefaultSystemProperty("zerox.join.progressive-view-distance", settings.getProperty("join.progressive-view-distance", "true"));\n'
    '        setDefaultSystemProperty("zerox.join.initial-send-distance", settings.getProperty("join.initial-send-distance", "3"));\n'
    '        setDefaultSystemProperty("zerox.join.ramp-interval-ticks", settings.getProperty("join.ramp-interval-ticks", "8"));\n'
    '        setDefaultSystemProperty("zerox.join.start-grace-ticks", settings.getProperty("join.start-grace-ticks", "10"));\n'
    '        setDefaultSystemProperty("zerox.join.max-ramp-steps-per-tick", settings.getProperty("join.max-ramp-steps-per-tick", "1"));\n'
    '        setDefaultSystemProperty("zerox.events.listener-warning-ms", settings.getProperty("events.listener-warning-ms", "15"));\n',
    "join-load system properties",
)
replace_once(
    bootstrap,
    "    private static void printRuntimeWarnings() {\n",
    r'''    private static void migrateJoinLoadSettings(final Properties settings) throws IOException {
        settings.putIfAbsent("join.progressive-view-distance", "true");
        settings.putIfAbsent("join.initial-send-distance", "3");
        settings.putIfAbsent("join.ramp-interval-ticks", "8");
        settings.putIfAbsent("join.start-grace-ticks", "10");
        settings.putIfAbsent("join.max-ramp-steps-per-tick", "1");
        settings.putIfAbsent("events.listener-warning-ms", "15");

        if (!Boolean.parseBoolean(settings.getProperty("migration.v4-2-join-load", "false"))) {
            final Path global = Path.of("config", "paper-global.yml");
            if (Files.isRegularFile(global)) {
                final java.util.List<String> lines = Files.readAllLines(global, StandardCharsets.UTF_8);
                final java.util.Map<String, String[]> migrations = new java.util.LinkedHashMap<>();
                migrations.put("player-max-chunk-send-rate", new String[]{"75.0", "35.0"});
                migrations.put("player-max-chunk-load-rate", new String[]{"100.0", "50.0"});
                migrations.put("player-max-chunk-generate-rate", new String[]{"-1.0", "12.0"});
                migrations.put("player-max-concurrent-chunk-loads", new String[]{"0", "4"});
                migrations.put("player-max-concurrent-chunk-generates", new String[]{"0", "2"});
                migrations.put("max-joins-per-tick", new String[]{"5", "1"});
                boolean changed = false;
                for (int index = 0; index < lines.size(); ++index) {
                    final String line = lines.get(index);
                    final int colon = line.indexOf(':');
                    if (colon < 0) continue;
                    final String key = line.substring(0, colon).trim();
                    final String[] migration = migrations.get(key);
                    if (migration == null) continue;
                    final String remainder = line.substring(colon + 1);
                    final int commentIndex = remainder.indexOf('#');
                    final String scalar = (commentIndex >= 0 ? remainder.substring(0, commentIndex) : remainder).trim();
                    if (!scalar.equals(migration[0])) continue;
                    final String comment = commentIndex >= 0 ? " " + remainder.substring(commentIndex).trim() : "";
                    lines.set(index, line.substring(0, colon + 1) + " " + migration[1] + comment);
                    changed = true;
                }
                if (changed) {
                    final Path backupDir = DIR.resolve("backups");
                    Files.createDirectories(backupDir);
                    final Path backup = backupDir.resolve("config_paper-global.yml.pre-v4.2.bak");
                    Files.copy(global, backup, StandardCopyOption.REPLACE_EXISTING);
                    Files.write(global, lines, StandardCharsets.UTF_8);
                    System.out.println("[ZEROX] Migrated Paper join/chunk burst defaults; backup=" + backup + ".");
                }
            }
            settings.setProperty("migration.v4-2-join-load", "true");
        }

        try (var out = Files.newOutputStream(SETTINGS)) {
            settings.store(out, "ZEROX Paper v4.2 semantic-preserving join-load profile");
        }
    }

    private static void printRuntimeWarnings() {
''',
    "join-load configuration migration",
)
replace_once(
    bootstrap,
    "        System.out.println(\"[ZEROX] Runtime profile: CPUs=\" + processors + \", chunk-workers=\"\n            + System.getProperty(\"Paper.WorkerThreadCount\") + \", netty=\"\n            + System.getProperty(\"io.netty.eventLoopThreads\") + \".\");\n",
    "        System.out.println(\"[ZEROX] Runtime profile: CPUs=\" + processors + \", chunk-workers=\"\n            + System.getProperty(\"Paper.WorkerThreadCount\") + \", netty=\"\n            + System.getProperty(\"io.netty.eventLoopThreads\") + \".\");\n"
    "        ZeroxJoinLoadController.reportConfiguration();\n",
    "join-load startup report",
)

build_info = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java")
replace_once(build_info, 'public static final String VERSION = "2.2.1";', 'public static final String VERSION = "2.2.2";', "v4.2 version")
replace_once(build_info, 'public static final int PATCH_COUNT = 7;', 'public static final int PATCH_COUNT = 8;', "v4.2 patch count")
replace_once(build_info, 'MINECRAFT_VERSION + "-v4.1 / "', 'MINECRAFT_VERSION + "-v4.2 / "', "visible v4.2 identity")

craft_server = require("paper-server/src/main/java/org/bukkit/craftbukkit/CraftServer.java")
replace_once(craft_server, "ZEROX Paper 1.21.11-v4.1", "ZEROX Paper 1.21.11-v4.2", "CraftServer v4.2 identity")

metadata_path = require("paper-server/src/main/resources/META-INF/zerox-build.json")
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata.update({
    "version": "2.2.2",
    "patchCount": 8,
    "progressiveJoinViewDistance": True,
    "initialJoinSendDistance": 3,
    "joinRampIntervalTicks": 8,
    "playerChunkSendRate": 35.0,
    "playerChunkLoadRate": 50.0,
    "playerChunkGenerateRate": 12.0,
    "playerConcurrentChunkLoads": 4,
    "playerConcurrentChunkGenerates": 2,
    "maxJoinsPerTick": 1,
    "slowSynchronousEventTelemetry": True,
    "unsafeSynchronousEventsParallelized": False,
    "joinWorkDropped": False,
})
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

print("ZEROX v4.2 safe join-load smoothing applied to", root)

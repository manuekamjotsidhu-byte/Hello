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


global_config = require("paper-server/src/main/java/io/papermc/paper/configuration/GlobalConfiguration.java")
for old, new, description in (
    (
        "public double playerMaxChunkSendRate = 35.0; // ZEROX v4.2: smooth join chunk delivery",
        "public double playerMaxChunkSendRate = 24.0; // ZEROX v4.3: high-density bounded chunk delivery",
        "density chunk send rate",
    ),
    (
        "public double playerMaxChunkLoadRate = 50.0; // ZEROX v4.2: bound per-player async chunk loads",
        "public double playerMaxChunkLoadRate = 36.0; // ZEROX v4.3: reserve CPU for the authoritative tick",
        "density chunk load rate",
    ),
    (
        "public double playerMaxChunkGenerateRate = 12.0; // ZEROX v4.2: bound per-player async generation",
        "public double playerMaxChunkGenerateRate = 8.0; // ZEROX v4.3: prevent generation storms",
        "density chunk generation rate",
    ),
    (
        "public int playerMaxConcurrentChunkLoads = 4; // ZEROX v4.2: use workers without a join burst",
        "public int playerMaxConcurrentChunkLoads = 3; // ZEROX v4.3: bounded per-player parallel loads",
        "density concurrent chunk loads",
    ),
    (
        "public int playerMaxConcurrentChunkGenerates = 2; // ZEROX v4.2: generation parallelism cap",
        "public int playerMaxConcurrentChunkGenerates = 1; // ZEROX v4.3: one generation pipeline per player",
        "density concurrent chunk generations",
    ),
):
    replace_once(global_config, old, new, description)

async_scheduler = require("paper-server/src/main/java/org/bukkit/craftbukkit/scheduler/CraftAsyncScheduler.java")
replace_once(
    async_scheduler,
    "    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(\n",
    "    private final ThreadPoolExecutor executor = new io.papermc.paper.zerox.ZeroxAdaptiveThreadPoolExecutor(\n",
    "adaptive async executor",
)
replace_once(
    async_scheduler,
    "            new ThreadPoolExecutor.CallerRunsPolicy());\n",
    "            new io.papermc.paper.zerox.ZeroxAsyncOverflowPolicy());\n",
    "off-main async overflow policy",
)

guard = require("paper-server/src/main/java/org/bukkit/craftbukkit/scheduler/ZeroxSchedulerGuard.java")
replace_once(
    guard,
    "    static void beginTick(final int tick) {\n        currentTick = tick;\n",
    "    static void beginTick(final int tick) {\n"
    "        io.papermc.paper.zerox.ZeroxMainThreadPressure.rollTick(tick);\n"
    "        currentTick = tick;\n",
    "main-thread pressure tick roll",
)
replace_once(
    guard,
    "        globalSpentNanos += elapsedNanos;\n",
    "        globalSpentNanos += elapsedNanos;\n"
    "        io.papermc.paper.zerox.ZeroxMainThreadPressure.recordSyncWork(elapsedNanos);\n",
    "scheduler pressure accounting",
)

registered_listener = require("paper-api/src/main/java/org/bukkit/plugin/RegisteredListener.java")
replace_once(
    registered_listener,
    "    private void zeroxRecordEventTime(final Event event, final long elapsedNanos) {\n"
    "        if (event.isAsynchronous() || elapsedNanos < ZEROX_EVENT_WARNING_NANOS) {\n",
    "    private void zeroxRecordEventTime(final Event event, final long elapsedNanos) {\n"
    "        if (!event.isAsynchronous()) {\n"
    "            io.papermc.paper.zerox.ZeroxMainThreadPressure.recordSyncWork(elapsedNanos);\n"
    "        }\n"
    "        if (event.isAsynchronous() || elapsedNanos < ZEROX_EVENT_WARNING_NANOS) {\n",
    "event pressure accounting",
)

join_controller = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxJoinLoadController.java")
replace_once(
    join_controller,
    "        if (!ENABLED || RAMPS.isEmpty()) {\n            return;\n        }\n\n        int steps = 0;\n",
    "        if (!ENABLED || RAMPS.isEmpty()) {\n"
    "            return;\n"
    "        }\n"
    "        if (ZeroxMainThreadPressure.shouldHoldJoinExpansion()) {\n"
    "            ZeroxMainThreadPressure.recordJoinHold();\n"
    "            return;\n"
    "        }\n\n"
    "        int steps = 0;\n",
    "pressure-aware join expansion",
)

repo = Path(__file__).resolve().parent.parent
pkg = root / "paper-server/src/main/java/io/papermc/paper/zerox"
pkg.mkdir(parents=True, exist_ok=True)
for name in (
    "ZeroxMainThreadPressure.java",
    "ZeroxAdaptiveThreadPoolExecutor.java",
    "ZeroxAsyncOverflowPolicy.java",
):
    template = repo / "templates" / "v4_3" / name
    if not template.is_file():
        raise SystemExit(f"Missing v4.3 template: {template}")
    (pkg / name).write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

bootstrap = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java")
replace_once(
    bootstrap,
    '            settings.setProperty("events.listener-warning-ms", "15");\n',
    '            settings.setProperty("events.listener-warning-ms", "15");\n'
    '            settings.setProperty("density.target-mspt", "20");\n'
    '            settings.setProperty("density.plugin-high-ms", "12");\n'
    '            settings.setProperty("density.plugin-critical-ms", "18");\n'
    '            settings.setProperty("density.join-hold-mspt", "18");\n'
    '            settings.setProperty("density.reserve-main-cores", "2");\n'
    '            settings.setProperty("density.async-overflow-queue", "16384");\n',
    "density defaults",
)
replace_once(
    bootstrap,
    "        migrateJoinLoadSettings(settings);\n\n        final int processors = Runtime.getRuntime().availableProcessors();\n",
    "        migrateJoinLoadSettings(settings);\n"
    "        migrateDensitySettings(settings);\n\n"
    "        final int processors = Runtime.getRuntime().availableProcessors();\n",
    "density migration invocation",
)
replace_once(
    bootstrap,
    'Math.max(2, Math.min(8, Math.max(1, processors / 2)))',
    'Math.max(1, Math.min(2, Math.max(1, processors / 3)))',
    "density async core auto sizing",
)
replace_once(
    bootstrap,
    'Math.max(4, Math.min(32, processors * 2))',
    'Math.max(2, Math.min(6, Math.max(2, processors - 2)))',
    "density async max auto sizing",
)
replace_once(
    bootstrap,
    '        setDefaultSystemProperty("zerox.events.listener-warning-ms", settings.getProperty("events.listener-warning-ms", "15"));\n',
    '        setDefaultSystemProperty("zerox.events.listener-warning-ms", settings.getProperty("events.listener-warning-ms", "15"));\n'
    '        setDefaultSystemProperty("zerox.density.target-mspt", settings.getProperty("density.target-mspt", "20"));\n'
    '        setDefaultSystemProperty("zerox.density.plugin-high-ms", settings.getProperty("density.plugin-high-ms", "12"));\n'
    '        setDefaultSystemProperty("zerox.density.plugin-critical-ms", settings.getProperty("density.plugin-critical-ms", "18"));\n'
    '        setDefaultSystemProperty("zerox.density.join-hold-mspt", settings.getProperty("density.join-hold-mspt", "18"));\n'
    '        setDefaultSystemProperty("zerox.density.reserve-main-cores", settings.getProperty("density.reserve-main-cores", "2"));\n'
    '        setDefaultSystemProperty("zerox.density.async-overflow-queue", settings.getProperty("density.async-overflow-queue", "16384"));\n',
    "density system properties",
)
replace_once(
    bootstrap,
    "    private static void printRuntimeWarnings() {\n",
    r'''    private static void migrateDensitySettings(final Properties settings) throws IOException {
        settings.putIfAbsent("density.target-mspt", "20");
        settings.putIfAbsent("density.plugin-high-ms", "12");
        settings.putIfAbsent("density.plugin-critical-ms", "18");
        settings.putIfAbsent("density.join-hold-mspt", "18");
        settings.putIfAbsent("density.reserve-main-cores", "2");
        settings.putIfAbsent("density.async-overflow-queue", "16384");

        if ("4096".equals(settings.getProperty("plugins.async-queue-capacity"))) {
            settings.setProperty("plugins.async-queue-capacity", "16384");
        }
        if ("15".equals(settings.getProperty("events.listener-warning-ms"))) {
            settings.setProperty("events.listener-warning-ms", "10");
        }

        if (!Boolean.parseBoolean(settings.getProperty("migration.v4-3-density", "false"))) {
            final Path global = Path.of("config", "paper-global.yml");
            if (Files.isRegularFile(global)) {
                final java.util.List<String> lines = Files.readAllLines(global, StandardCharsets.UTF_8);
                final java.util.Map<String, String[]> migrations = new java.util.LinkedHashMap<>();
                migrations.put("player-max-chunk-send-rate", new String[]{"35.0", "24.0"});
                migrations.put("player-max-chunk-load-rate", new String[]{"50.0", "36.0"});
                migrations.put("player-max-chunk-generate-rate", new String[]{"12.0", "8.0"});
                migrations.put("player-max-concurrent-chunk-loads", new String[]{"4", "3"});
                migrations.put("player-max-concurrent-chunk-generates", new String[]{"2", "1"});
                boolean changed = false;
                for (int index = 0; index < lines.size(); ++index) {
                    final String line = lines.get(index);
                    final int colon = line.indexOf(':');
                    if (colon < 0) continue;
                    final String key = line.substring(0, colon).trim();
                    final String[] migration = migrations.get(key);
                    if (migration == null || !line.substring(colon + 1).trim().equals(migration[0])) continue;
                    lines.set(index, line.substring(0, colon + 1) + " " + migration[1]);
                    changed = true;
                }
                if (changed) {
                    final Path backup = DIR.resolve("backups").resolve("config_paper-global.yml.pre-v4.3.bak");
                    Files.createDirectories(backup.getParent());
                    if (!Files.exists(backup)) Files.copy(global, backup);
                    Files.write(global, lines, StandardCharsets.UTF_8);
                    System.out.println("[ZEROX] Migrated v4.2 chunk admission values to the v4.3 high-density profile; backup=" + backup + ".");
                }
            }
            settings.setProperty("migration.v4-3-density", "true");
        }

        try (var out = Files.newOutputStream(SETTINGS)) {
            settings.store(out, "ZEROX Paper v4.3 high-density profile");
        }
    }

    private static void printRuntimeWarnings() {
''',
    "density migration method",
)
replace_once(
    bootstrap,
    "12G is recommended for a 16G container.",
    "Use 6G for an 8G container or 12G for a 16G container.",
    "8 GiB heap guidance",
)
replace_once(
    bootstrap,
    "        ZeroxJoinLoadController.reportConfiguration();\n",
    "        ZeroxJoinLoadController.reportConfiguration();\n"
    "        ZeroxMainThreadPressure.reportConfiguration();\n",
    "density startup report",
)

build_info = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java")
replace_once(build_info, 'public static final String VERSION = "2.2.2";', 'public static final String VERSION = "2.3.0";', "v4.3 version")
replace_once(build_info, 'public static final int PATCH_COUNT = 8;', 'public static final int PATCH_COUNT = 9;', "v4.3 patch count")
replace_once(build_info, 'MINECRAFT_VERSION + "-v4.2 / "', 'MINECRAFT_VERSION + "-v4.3 / "', "visible v4.3 identity")

craft_server = require("paper-server/src/main/java/org/bukkit/craftbukkit/CraftServer.java")
replace_once(craft_server, "ZEROX Paper 1.21.11-v4.2", "ZEROX Paper 1.21.11-v4.3", "CraftServer v4.3 identity")

metadata_path = require("paper-server/src/main/resources/META-INF/zerox-build.json")
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata.update({
    "version": "2.3.0",
    "patchCount": 9,
    "highDensityProfile": True,
    "targetPlayers": "200-300 requires workload validation; not guaranteed",
    "targetMspt": 20,
    "callerRunsPolicyRemoved": True,
    "asyncWorkRunsOnMainThreadWhenSaturated": False,
    "asyncOverflowQueue": 16384,
    "adaptiveAsyncConcurrency": True,
    "reservedMainCores": 2,
    "playerChunkSendRate": 24.0,
    "playerChunkLoadRate": 36.0,
    "playerChunkGenerateRate": 8.0,
    "playerConcurrentChunkLoads": 3,
    "playerConcurrentChunkGenerates": 1,
    "workDropped": False,
    "unsafeSynchronousWorkAutomaticallyParallelized": False,
})
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

print("ZEROX v4.3 high-density backpressure and adaptive async execution applied to", root)

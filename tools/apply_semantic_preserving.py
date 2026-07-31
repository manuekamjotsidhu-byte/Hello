#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()


def require(path: str) -> Path:
    target = root / path
    if not target.is_file():
        raise SystemExit(f"Required file not found: {target}")
    return target


def replace_once(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch point missing for {description}: {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Restore upstream gameplay semantics for defaults that can change observable behavior.
world = require("paper-server/src/main/java/io/papermc/paper/configuration/WorldConfiguration.java")
replace_once(
    world,
    "public boolean doCollisionEntityLookups = false; // ZEROX: avoid unnecessary armor-stand collision scans",
    "public boolean doCollisionEntityLookups = true; // ZEROX v4: preserve upstream armor-stand collision behavior",
    "armor stand collision semantics",
)
replace_once(
    world,
    "public boolean updatePathfindingOnBlockUpdate = false; // ZEROX: avoid pathfinding recalculation storms",
    "public boolean updatePathfindingOnBlockUpdate = true; // ZEROX v4: preserve upstream pathfinding behavior",
    "pathfinding semantics",
)

spigot = require("paper-server/src/main/java/org/spigotmc/SpigotWorldConfig.java")
replace_once(
    spigot,
    'this.maxTntTicksPerTick = this.getInt("max-tnt-per-tick", 16); // ZEROX: bound TNT entity work per tick',
    'this.maxTntTicksPerTick = this.getInt("max-tnt-per-tick", 100); // ZEROX v4: preserve upstream TNT timing by default',
    "TNT timing semantics",
)

# Keep the optional emergency limiter, but disable it whenever semantic-preserving mode is active.
limiter = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxExplosionLimiter.java")
replace_once(
    limiter,
    "public final class ZeroxExplosionLimiter {\n    private static final Map<ServerLevel, Budget> BUDGETS = new WeakHashMap<>();\n",
    "public final class ZeroxExplosionLimiter {\n"
    "    private static final Map<ServerLevel, Budget> BUDGETS = new WeakHashMap<>();\n"
    "    private static final boolean PRESERVE_SEMANTICS = Boolean.parseBoolean(\n"
    "        System.getProperty(\"zerox.behavior.preserve-semantics\", \"true\")\n"
    "    );\n"
    "    private static final boolean LOAD_SHEDDING_ENABLED = !PRESERVE_SEMANTICS && Boolean.parseBoolean(\n"
    "        System.getProperty(\"zerox.tnt.load-shedding-enabled\", \"false\")\n"
    "    );\n",
    "TNT semantic mode fields",
)
replace_once(
    limiter,
    "    public static synchronized boolean tryAcquire(final ServerLevel level) {\n        final long tick = level.getGameTime();\n",
    "    public static synchronized boolean tryAcquire(final ServerLevel level) {\n"
    "        if (!LOAD_SHEDDING_ENABLED) {\n"
    "            return true;\n"
    "        }\n"
    "        final long tick = level.getGameTime();\n",
    "TNT semantic-mode bypass",
)
replace_once(
    limiter,
    "    public static int maxExplosionsPerTick() {\n",
    "    public static boolean loadSheddingEnabled() {\n"
    "        return LOAD_SHEDDING_ENABLED;\n"
    "    }\n\n"
    "    public static int maxExplosionsPerTick() {\n",
    "TNT limiter status accessor",
)

# Retain timing telemetry, but never defer real synchronous plugin work in the default mode.
guard = require("paper-server/src/main/java/org/bukkit/craftbukkit/scheduler/ZeroxSchedulerGuard.java")
replace_once(
    guard,
    '    private static final boolean DEFER_REPEATING = Boolean.parseBoolean(System.getProperty("zerox.plugins.defer-repeating-tasks", "true"));\n',
    '    private static final boolean PRESERVE_SEMANTICS = Boolean.parseBoolean(System.getProperty("zerox.behavior.preserve-semantics", "true"));\n'
    '    private static final boolean DEFER_REPEATING = !PRESERVE_SEMANTICS && Boolean.parseBoolean(System.getProperty("zerox.plugins.defer-repeating-tasks", "false"));\n',
    "sync scheduler semantic mode",
)
replace_once(
    guard,
    "        if (state.spentThisTick > PLUGIN_BUDGET_NANOS) {\n",
    "        if (DEFER_REPEATING && state.spentThisTick > PLUGIN_BUDGET_NANOS) {\n",
    "disable scheduler debt in semantic mode",
)
replace_once(
    guard,
    '                    + "ms; repeating executions will be delayed to protect TPS.");\n',
    '                    + "ms; " + (DEFER_REPEATING\n'
    '                        ? "repeating executions may be delayed by the optional protection mode."\n'
    '                        : "execution was preserved; optimize or update this plugin task."));\n',
    "semantic-aware slow-task warning",
)
replace_once(
    guard,
    '            + ASYNC_CORE + "-" + ASYNC_MAX + " threads, queue=" + ASYNC_QUEUE + ".");\n',
    '            + ASYNC_CORE + "-" + ASYNC_MAX + " threads, queue=" + ASYNC_QUEUE\n'
    '            + ", preserve-semantics=" + PRESERVE_SEMANTICS + ".");\n',
    "semantic mode scheduler report",
)

bootstrap = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java")
replace_once(
    bootstrap,
    '            settings.setProperty("plugins.sync-global-budget-ms", "6");\n',
    '            settings.setProperty("behavior.preserve-semantics", "true");\n'
    '            settings.setProperty("tnt.load-shedding-enabled", "false");\n'
    '            settings.setProperty("plugins.sync-global-budget-ms", "6");\n',
    "semantic-preserving generated settings",
)
replace_once(
    bootstrap,
    '        setDefaultSystemProperty("zerox.plugins.sync-global-budget-ms", settings.getProperty("plugins.sync-global-budget-ms", "6"));\n',
    '        setDefaultSystemProperty("zerox.behavior.preserve-semantics", settings.getProperty("behavior.preserve-semantics", "true"));\n'
    '        setDefaultSystemProperty("zerox.tnt.load-shedding-enabled", settings.getProperty("tnt.load-shedding-enabled", "false"));\n'
    '        setDefaultSystemProperty("zerox.plugins.sync-global-budget-ms", settings.getProperty("plugins.sync-global-budget-ms", "6"));\n',
    "semantic-preserving runtime properties",
)
replace_once(
    bootstrap,
    'settings.getProperty("plugins.defer-repeating-tasks", "true")',
    'settings.getProperty("plugins.defer-repeating-tasks", "false")',
    "non-deferring scheduler fallback",
)
replace_once(
    bootstrap,
    'profileVersion=3\\n",',
    'profileVersion=4\\n",',
    "profile version",
)
replace_once(
    bootstrap,
    "ZEROX Paper performance profile v3",
    "ZEROX Paper performance profile v4 semantic-preserving",
    "profile comment",
)
replace_once(
    bootstrap,
    '            + zeroxStartupMillis + "ms); TNT budget="\n'
    '            + ZeroxExplosionLimiter.maxExplosionsPerTick() + " explosions/"\n'
    '            + ZeroxExplosionLimiter.maxProcessingMillisPerTick() + "ms per tick.");\n',
    '            + zeroxStartupMillis + "ms); semantic-preserving="\n'
    '            + System.getProperty("zerox.behavior.preserve-semantics", "true")\n'
    '            + ", TNT load-shedding=" + ZeroxExplosionLimiter.loadSheddingEnabled() + ".");\n',
    "readiness semantic status",
)

build_info = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java")
replace_once(build_info, 'public static final String VERSION = "2.1.0";', 'public static final String VERSION = "2.2.0";', "v4 version")
replace_once(build_info, 'public static final int PATCH_COUNT = 5;', 'public static final int PATCH_COUNT = 6;', "v4 patch count")
replace_once(build_info, 'MINECRAFT_VERSION + "-v3 / "', 'MINECRAFT_VERSION + "-v4 / "', "visible v4 identity")

craft_server = require("paper-server/src/main/java/org/bukkit/craftbukkit/CraftServer.java")
replace_once(craft_server, "ZEROX Paper 1.21.11-v3", "ZEROX Paper 1.21.11-v4", "CraftServer v4 identity")

metadata_path = require("paper-server/src/main/resources/META-INF/zerox-build.json")
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata.update({
    "version": "2.2.0",
    "patchCount": 6,
    "semanticPreservingDefault": True,
    "syncTaskDeferralDefault": False,
    "tntLoadSheddingDefault": False,
    "gameplayDefaultsPreserved": True,
    "safeParallelismScope": "existing asynchronous plugin tasks and Paper worker systems",
})
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

print("ZEROX v4 semantic-preserving optimization mode applied to", root)

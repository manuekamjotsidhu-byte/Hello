#!/usr/bin/env python3
from pathlib import Path
import sys

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


scheduler = require("paper-server/src/main/java/org/bukkit/craftbukkit/scheduler/CraftScheduler.java")
replace_once(
    scheduler,
    "        this.currentTick++;\n",
    "        this.currentTick++;\n        ZeroxSchedulerGuard.beginTick(this.currentTick); // ZEROX\n",
    "scheduler tick budget reset",
)
replace_once(
    scheduler,
    "            if (task.isSync()) {\n                this.currentTask = task;\n",
    "            if (task.isSync()) {\n"
    "                if (ZeroxSchedulerGuard.shouldDefer(task, this.currentTick)) {\n"
    "                    task.setNextRun(this.currentTick + 1L);\n"
    "                    temp.add(task);\n"
    "                    this.parsePending();\n"
    "                    continue;\n"
    "                }\n"
    "                this.currentTask = task;\n"
    "                final long zeroxTaskStart = System.nanoTime();\n",
    "sync task pre-execution guard",
)
replace_once(
    scheduler,
    "                } finally {\n                    this.currentTask = null;\n                }\n",
    "                } finally {\n"
    "                    ZeroxSchedulerGuard.record(task, System.nanoTime() - zeroxTaskStart, this.currentTick);\n"
    "                    this.currentTask = null;\n"
    "                }\n",
    "sync task timing record",
)

async_scheduler = require("paper-server/src/main/java/org/bukkit/craftbukkit/scheduler/CraftAsyncScheduler.java")
replace_once(
    async_scheduler,
    "import java.util.concurrent.SynchronousQueue;\n",
    "import java.util.concurrent.LinkedBlockingQueue;\n",
    "bounded async queue import",
)
replace_once(
    async_scheduler,
    "    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(\n"
    "            4, Integer.MAX_VALUE, 30L, TimeUnit.SECONDS, new SynchronousQueue<>(),\n"
    "            new ThreadFactoryBuilder().setNameFormat(\"Craft Scheduler Thread - %1$d\").build());\n",
    "    private final ThreadPoolExecutor executor = new ThreadPoolExecutor(\n"
    "            ZeroxSchedulerGuard.asyncCoreThreads(),\n"
    "            ZeroxSchedulerGuard.asyncMaxThreads(),\n"
    "            30L, TimeUnit.SECONDS,\n"
    "            new LinkedBlockingQueue<>(ZeroxSchedulerGuard.asyncQueueCapacity()),\n"
    "            new ThreadFactoryBuilder().setNameFormat(\"ZEROX Plugin Async - %1$d\").build(),\n"
    "            new ThreadPoolExecutor.CallerRunsPolicy());\n",
    "bounded async plugin executor",
)
replace_once(
    async_scheduler,
    "        executor.prestartAllCoreThreads();\n",
    "        executor.prestartAllCoreThreads();\n        ZeroxSchedulerGuard.reportAsyncPool(); // ZEROX\n",
    "async pool startup report",
)

pkg = root / "paper-server/src/main/java/org/bukkit/craftbukkit/scheduler"
(pkg / "ZeroxSchedulerGuard.java").write_text(r'''package org.bukkit.craftbukkit.scheduler;

import java.util.Map;
import java.util.WeakHashMap;
import java.util.concurrent.TimeUnit;
import org.bukkit.plugin.Plugin;

final class ZeroxSchedulerGuard {
    private static final long GLOBAL_BUDGET_NANOS = TimeUnit.MILLISECONDS.toNanos(intProperty("zerox.plugins.sync-global-budget-ms", 6, 1, 40));
    private static final long PLUGIN_BUDGET_NANOS = TimeUnit.MILLISECONDS.toNanos(intProperty("zerox.plugins.sync-per-plugin-budget-ms", 3, 1, 30));
    private static final long WARNING_NANOS = TimeUnit.MILLISECONDS.toNanos(intProperty("zerox.plugins.sync-task-warning-ms", 10, 1, 1000));
    private static final int MAX_PENALTY_TICKS = intProperty("zerox.plugins.max-penalty-ticks", 20, 1, 200);
    private static final boolean DEFER_REPEATING = Boolean.parseBoolean(System.getProperty("zerox.plugins.defer-repeating-tasks", "true"));
    private static final boolean LOG_OVERRUNS = Boolean.parseBoolean(System.getProperty("zerox.plugins.log-overruns", "true"));
    private static final int ASYNC_CORE = intProperty("zerox.plugins.async-core-threads", autoAsyncCore(), 1, 64);
    private static final int ASYNC_MAX = Math.max(ASYNC_CORE, intProperty("zerox.plugins.async-max-threads", autoAsyncMax(), ASYNC_CORE, 128));
    private static final int ASYNC_QUEUE = intProperty("zerox.plugins.async-queue-capacity", 4096, 64, 65536);
    private static final Map<Plugin, PluginState> STATES = new WeakHashMap<>();
    private static int currentTick;
    private static long globalSpentNanos;

    private ZeroxSchedulerGuard() {}

    static void beginTick(final int tick) {
        currentTick = tick;
        globalSpentNanos = 0L;
        for (PluginState state : STATES.values()) {
            state.spentThisTick = 0L;
        }
    }

    static boolean shouldDefer(final CraftTask task, final int tick) {
        if (!DEFER_REPEATING || task.getPeriod() <= 0L || task.getOwner() == null) {
            return false;
        }
        final PluginState state = STATES.computeIfAbsent(task.getOwner(), ignored -> new PluginState());
        final boolean defer = tick < state.penaltyUntilTick
            || globalSpentNanos >= GLOBAL_BUDGET_NANOS
            || state.spentThisTick >= PLUGIN_BUDGET_NANOS;
        if (defer) {
            state.deferred++;
            maybeLogDeferred(task, state);
        }
        return defer;
    }

    static void record(final CraftTask task, final long elapsedNanos, final int tick) {
        if (task.getOwner() == null) {
            return;
        }
        final PluginState state = STATES.computeIfAbsent(task.getOwner(), ignored -> new PluginState());
        state.spentThisTick += elapsedNanos;
        globalSpentNanos += elapsedNanos;

        if (state.spentThisTick > PLUGIN_BUDGET_NANOS) {
            final long excess = state.spentThisTick - PLUGIN_BUDGET_NANOS;
            final int penalty = Math.min(MAX_PENALTY_TICKS, Math.max(1, (int) ((excess + PLUGIN_BUDGET_NANOS - 1L) / PLUGIN_BUDGET_NANOS)));
            state.penaltyUntilTick = Math.max(state.penaltyUntilTick, tick + penalty + 1);
        }

        if (LOG_OVERRUNS && elapsedNanos >= WARNING_NANOS) {
            final long now = System.nanoTime();
            if (now - state.lastWarningNanos >= TimeUnit.SECONDS.toNanos(5)) {
                final Class<?> taskClass = task.getTaskClass();
                task.getOwner().getLogger().warning("[ZEROX] Main-thread task #" + task.getTaskId()
                    + " (" + (taskClass == null ? "unknown" : taskClass.getName()) + ") took "
                    + String.format(java.util.Locale.ROOT, "%.2f", elapsedNanos / 1_000_000.0D)
                    + "ms; repeating executions will be delayed to protect TPS.");
                state.lastWarningNanos = now;
            }
        }
    }

    private static void maybeLogDeferred(final CraftTask task, final PluginState state) {
        if (!LOG_OVERRUNS) {
            return;
        }
        final long now = System.nanoTime();
        if (now - state.lastDeferralLogNanos >= TimeUnit.SECONDS.toNanos(5)) {
            task.getOwner().getLogger().warning("[ZEROX] Deferred " + state.deferred
                + " repeating main-thread task execution(s); plugin budget="
                + TimeUnit.NANOSECONDS.toMillis(PLUGIN_BUDGET_NANOS) + "ms, global scheduler budget="
                + TimeUnit.NANOSECONDS.toMillis(GLOBAL_BUDGET_NANOS) + "ms per tick.");
            state.deferred = 0L;
            state.lastDeferralLogNanos = now;
        }
    }

    static int asyncCoreThreads() {
        return ASYNC_CORE;
    }

    static int asyncMaxThreads() {
        return ASYNC_MAX;
    }

    static int asyncQueueCapacity() {
        return ASYNC_QUEUE;
    }

    static void reportAsyncPool() {
        System.out.println("[ZEROX] Plugin scheduler: sync="
            + TimeUnit.NANOSECONDS.toMillis(GLOBAL_BUDGET_NANOS) + "ms global/"
            + TimeUnit.NANOSECONDS.toMillis(PLUGIN_BUDGET_NANOS) + "ms per plugin; async="
            + ASYNC_CORE + "-" + ASYNC_MAX + " threads, queue=" + ASYNC_QUEUE + ".");
    }

    private static int autoAsyncCore() {
        final int processors = Runtime.getRuntime().availableProcessors();
        return Math.max(2, Math.min(8, Math.max(1, processors / 2)));
    }

    private static int autoAsyncMax() {
        final int processors = Runtime.getRuntime().availableProcessors();
        return Math.max(autoAsyncCore(), Math.min(32, Math.max(4, processors * 2)));
    }

    private static int intProperty(final String key, final int fallback, final int minimum, final int maximum) {
        try {
            return Math.max(minimum, Math.min(maximum, Integer.parseInt(System.getProperty(key, Integer.toString(fallback)))));
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static final class PluginState {
        private long spentThisTick;
        private int penaltyUntilTick;
        private long deferred;
        private long lastWarningNanos;
        private long lastDeferralLogNanos;
    }
}
''', encoding="utf-8")

bootstrap = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java")
replace_once(
    bootstrap,
    '            settings.setProperty("tnt.log-deferrals", "true");\n',
    '            settings.setProperty("tnt.log-deferrals", "true");\n'
    '            settings.setProperty("plugins.sync-global-budget-ms", "6");\n'
    '            settings.setProperty("plugins.sync-per-plugin-budget-ms", "3");\n'
    '            settings.setProperty("plugins.sync-task-warning-ms", "10");\n'
    '            settings.setProperty("plugins.max-penalty-ticks", "20");\n'
    '            settings.setProperty("plugins.defer-repeating-tasks", "true");\n'
    '            settings.setProperty("plugins.log-overruns", "true");\n'
    '            settings.setProperty("plugins.async-core-threads", "auto");\n'
    '            settings.setProperty("plugins.async-max-threads", "auto");\n'
    '            settings.setProperty("plugins.async-queue-capacity", "4096");\n',
    "plugin scheduler defaults",
)
replace_once(
    bootstrap,
    '        setDefaultSystemProperty("zerox.tnt.log-deferrals", settings.getProperty("tnt.log-deferrals", "true"));\n',
    '        setDefaultSystemProperty("zerox.tnt.log-deferrals", settings.getProperty("tnt.log-deferrals", "true"));\n'
    '        setDefaultSystemProperty("zerox.plugins.sync-global-budget-ms", settings.getProperty("plugins.sync-global-budget-ms", "6"));\n'
    '        setDefaultSystemProperty("zerox.plugins.sync-per-plugin-budget-ms", settings.getProperty("plugins.sync-per-plugin-budget-ms", "3"));\n'
    '        setDefaultSystemProperty("zerox.plugins.sync-task-warning-ms", settings.getProperty("plugins.sync-task-warning-ms", "10"));\n'
    '        setDefaultSystemProperty("zerox.plugins.max-penalty-ticks", settings.getProperty("plugins.max-penalty-ticks", "20"));\n'
    '        setDefaultSystemProperty("zerox.plugins.defer-repeating-tasks", settings.getProperty("plugins.defer-repeating-tasks", "true"));\n'
    '        setDefaultSystemProperty("zerox.plugins.log-overruns", settings.getProperty("plugins.log-overruns", "true"));\n'
    '        setDefaultSystemProperty("zerox.plugins.async-core-threads", resolveAuto(settings.getProperty("plugins.async-core-threads", "auto"), Math.max(2, Math.min(8, Math.max(1, processors / 2)))));\n'
    '        setDefaultSystemProperty("zerox.plugins.async-max-threads", resolveAuto(settings.getProperty("plugins.async-max-threads", "auto"), Math.max(4, Math.min(32, processors * 2))));\n'
    '        setDefaultSystemProperty("zerox.plugins.async-queue-capacity", settings.getProperty("plugins.async-queue-capacity", "4096"));\n',
    "plugin scheduler system properties",
)
replace_once(
    bootstrap,
    '    private static int parseInt(final String value, final int fallback) {\n',
    '    private static String resolveAuto(final String value, final int automatic) {\n'
    '        return value.equalsIgnoreCase("auto") ? Integer.toString(automatic) : value;\n'
    '    }\n\n'
    '    private static int parseInt(final String value, final int fallback) {\n',
    "auto plugin thread resolver",
)

print("ZEROX v3 plugin parallelism and main-thread load guard applied to", root)

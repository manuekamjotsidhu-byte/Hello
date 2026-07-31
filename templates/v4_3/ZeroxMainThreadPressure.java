package io.papermc.paper.zerox;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;
import org.bukkit.Bukkit;

public final class ZeroxMainThreadPressure {
    private static final long TARGET_NANOS = TimeUnit.MILLISECONDS.toNanos(intProperty("zerox.density.target-mspt", 20, 5, 45));
    private static final long PLUGIN_HIGH_NANOS = TimeUnit.MILLISECONDS.toNanos(intProperty("zerox.density.plugin-high-ms", 12, 1, 40));
    private static final long PLUGIN_CRITICAL_NANOS = TimeUnit.MILLISECONDS.toNanos(intProperty("zerox.density.plugin-critical-ms", 18, 2, 45));
    private static final double JOIN_HOLD_MSPT = doubleProperty("zerox.density.join-hold-mspt", 18.0D, 5.0D, 45.0D);
    private static final int RESERVED_CORES = intProperty("zerox.density.reserve-main-cores", 2, 1, 8);
    private static final AtomicInteger ASYNC_ACTIVE = new AtomicInteger();
    private static volatile long currentSyncNanos;
    private static volatile long previousSyncNanos;
    private static volatile double ewmaSyncNanos;
    private static volatile int currentTick;
    private static volatile int lastReportedLimit = -1;
    private static volatile long lastLimitLogNanos;
    private static volatile long joinHolds;
    private static volatile long lastJoinHoldLogNanos;

    private ZeroxMainThreadPressure() {}

    public static void rollTick(final int tick) {
        if (tick == currentTick) return;
        previousSyncNanos = currentSyncNanos;
        ewmaSyncNanos = ewmaSyncNanos == 0.0D ? previousSyncNanos : (ewmaSyncNanos * 0.85D) + (previousSyncNanos * 0.15D);
        currentSyncNanos = 0L;
        currentTick = tick;
    }

    public static void recordSyncWork(final long elapsedNanos) {
        if (elapsedNanos > 0L) currentSyncNanos += elapsedNanos;
    }

    public static void acquireAsyncSlot(final int configuredMaximum) {
        while (true) {
            final int limit = asyncConcurrencyLimit(configuredMaximum);
            final int active = ASYNC_ACTIVE.get();
            if (active < limit && ASYNC_ACTIVE.compareAndSet(active, active + 1)) return;
            LockSupport.parkNanos(TimeUnit.MICROSECONDS.toNanos(250L));
        }
    }

    public static void releaseAsyncSlot() {
        ASYNC_ACTIVE.updateAndGet(value -> Math.max(0, value - 1));
    }

    public static int asyncConcurrencyLimit(final int configuredMaximum) {
        final int processors = Math.max(1, Runtime.getRuntime().availableProcessors());
        final int hardMaximum = Math.max(1, Math.min(configuredMaximum, Math.max(1, processors - RESERVED_CORES)));
        final double mspt = averageTickMillis();
        final long pluginNanos = Math.max(previousSyncNanos, (long) ewmaSyncNanos);
        final int limit = (mspt >= TARGET_NANOS / 1_000_000.0D || pluginNanos >= PLUGIN_CRITICAL_NANOS)
            ? 1
            : (mspt >= 15.0D || pluginNanos >= PLUGIN_HIGH_NANOS ? Math.max(1, hardMaximum / 2) : hardMaximum);
        maybeReportLimit(limit, configuredMaximum, mspt, pluginNanos);
        return limit;
    }

    public static boolean shouldHoldJoinExpansion() {
        return averageTickMillis() >= JOIN_HOLD_MSPT || Math.max(previousSyncNanos, (long) ewmaSyncNanos) >= PLUGIN_HIGH_NANOS;
    }

    public static void recordJoinHold() {
        joinHolds++;
        final long now = System.nanoTime();
        if (now - lastJoinHoldLogNanos >= TimeUnit.SECONDS.toNanos(10L)) {
            System.out.println("[ZEROX] Join chunk expansion paused under main-thread pressure; " + joinHolds + " ramp tick(s) retained for later execution.");
            joinHolds = 0L;
            lastJoinHoldLogNanos = now;
        }
    }

    public static void reportConfiguration() {
        System.out.println("[ZEROX] High-density controller: target-mspt=" + TimeUnit.NANOSECONDS.toMillis(TARGET_NANOS)
            + ", join-hold-mspt=" + JOIN_HOLD_MSPT + ", reserve-main-cores=" + RESERVED_CORES
            + ", async work is delayed rather than run on the main thread.");
    }

    private static double averageTickMillis() {
        try { return Math.max(0.0D, Bukkit.getAverageTickTime()); } catch (Throwable ignored) { return 0.0D; }
    }

    private static void maybeReportLimit(final int limit, final int configuredMaximum, final double mspt, final long pluginNanos) {
        final long now = System.nanoTime();
        if (limit == lastReportedLimit || now - lastLimitLogNanos < TimeUnit.SECONDS.toNanos(5L)) return;
        lastReportedLimit = limit;
        lastLimitLogNanos = now;
        System.out.println("[ZEROX] Async plugin concurrency=" + limit + "/" + configuredMaximum
            + " (MSPT=" + String.format(java.util.Locale.ROOT, "%.2f", mspt)
            + ", sync-plugin=" + String.format(java.util.Locale.ROOT, "%.2f", pluginNanos / 1_000_000.0D) + "ms).");
    }

    private static int intProperty(final String key, final int fallback, final int minimum, final int maximum) {
        try { return Math.max(minimum, Math.min(maximum, Integer.parseInt(System.getProperty(key, Integer.toString(fallback))))); }
        catch (NumberFormatException ignored) { return fallback; }
    }

    private static double doubleProperty(final String key, final double fallback, final double minimum, final double maximum) {
        try { return Math.max(minimum, Math.min(maximum, Double.parseDouble(System.getProperty(key, Double.toString(fallback))))); }
        catch (NumberFormatException ignored) { return fallback; }
    }
}

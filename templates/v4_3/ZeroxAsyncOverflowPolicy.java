package io.papermc.paper.zerox;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ZeroxAsyncOverflowPolicy implements RejectedExecutionHandler {
    private final ArrayBlockingQueue<Runnable> overflow = new ArrayBlockingQueue<>(
        intProperty("zerox.density.async-overflow-queue", 16384, 256, 65536)
    );
    private final AtomicBoolean started = new AtomicBoolean();
    private volatile ThreadPoolExecutor target;
    private volatile long accepted;
    private volatile long lastLogNanos;

    @Override
    public void rejectedExecution(final Runnable task, final ThreadPoolExecutor executor) {
        if (executor.isShutdown()) throw new RejectedExecutionException("ZEROX async executor is shut down");
        this.target = executor;
        this.startDispatcher();
        try {
            if (!this.overflow.offer(task, 5L, TimeUnit.MILLISECONDS)) this.overflow.put(task);
            this.accepted++;
            this.maybeLog();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new RejectedExecutionException("Interrupted while preserving async plugin work", ex);
        }
    }

    private void startDispatcher() {
        if (!this.started.compareAndSet(false, true)) return;
        Thread.ofPlatform().daemon(true).name("ZEROX Async Overflow Dispatcher").start(() -> {
            while (true) {
                try {
                    final Runnable task = this.overflow.take();
                    ThreadPoolExecutor executor;
                    while ((executor = this.target) == null || executor.isShutdown()) TimeUnit.MILLISECONDS.sleep(10L);
                    executor.getQueue().put(task);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        });
    }

    private void maybeLog() {
        final long now = System.nanoTime();
        if (now - this.lastLogNanos < TimeUnit.SECONDS.toNanos(5L)) return;
        this.lastLogNanos = now;
        System.out.println("[ZEROX] Async overflow queue engaged: depth=" + this.overflow.size()
            + ", preserved=" + this.accepted + "; no task was executed on the main thread or dropped.");
    }

    private static int intProperty(final String key, final int fallback, final int minimum, final int maximum) {
        try { return Math.max(minimum, Math.min(maximum, Integer.parseInt(System.getProperty(key, Integer.toString(fallback))))); }
        catch (NumberFormatException ignored) { return fallback; }
    }
}

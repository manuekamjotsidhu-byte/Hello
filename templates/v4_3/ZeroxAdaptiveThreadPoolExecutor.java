package io.papermc.paper.zerox;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class ZeroxAdaptiveThreadPoolExecutor extends ThreadPoolExecutor {
    public ZeroxAdaptiveThreadPoolExecutor(
        final int corePoolSize,
        final int maximumPoolSize,
        final long keepAliveTime,
        final TimeUnit unit,
        final BlockingQueue<Runnable> workQueue,
        final ThreadFactory threadFactory,
        final RejectedExecutionHandler handler
    ) {
        super(corePoolSize, maximumPoolSize, keepAliveTime, unit, workQueue, threadFactory, handler);
    }

    @Override
    protected void beforeExecute(final Thread thread, final Runnable task) {
        ZeroxMainThreadPressure.acquireAsyncSlot(this.getMaximumPoolSize());
        super.beforeExecute(thread, task);
    }

    @Override
    protected void afterExecute(final Runnable task, final Throwable throwable) {
        try {
            super.afterExecute(task, throwable);
        } finally {
            ZeroxMainThreadPressure.releaseAsyncSlot();
        }
    }
}

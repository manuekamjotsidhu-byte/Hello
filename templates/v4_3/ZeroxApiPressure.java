package io.papermc.paper.zerox;

import java.util.concurrent.atomic.LongAdder;

/** Internal bridge for recording synchronous Bukkit listener time in paper-api. */
public final class ZeroxApiPressure {
    private static final LongAdder SYNC_EVENT_NANOS = new LongAdder();

    private ZeroxApiPressure() {}

    public static void recordSyncEvent(final long elapsedNanos) {
        if (elapsedNanos > 0L) {
            SYNC_EVENT_NANOS.add(elapsedNanos);
        }
    }

    public static long drainSyncEventNanos() {
        return SYNC_EVENT_NANOS.sumThenReset();
    }
}

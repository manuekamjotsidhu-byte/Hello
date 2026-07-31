# ZEROX Paper performance evidence

## User-observed baseline

The supplied Pterodactyl test used Paper 1.21.11, Java 25, a 512 MiB heap, zero plugins and one player.

Before the large TNT chain:

- median MSPT: approximately 5.7–7.4 ms;
- short-window p95 MSPT: approximately 8.1–10.5 ms;
- TPS: approximately 20.0.

After creating 30,870 TNT blocks, one-minute TPS fell through:

`19.1, 17.6, 16.7, 16.0, 15.2, 14.4, 13.6, 11.9`

This demonstrates that unlimited real work can exceed one server tick. It does not justify silently changing gameplay timing.

## ZEROX v4 acceptance test

GitHub Actions builds the fork from pinned Paper build 132 source and starts the real Paperclip jar on Java 21.

A synthetic plugin creates:

- one repeating synchronous task that sleeps for approximately 12 ms every tick;
- 32 Bukkit asynchronous tasks;
- counters for synchronous execution cadence and maximum async concurrency.

The build passes only when all of these are true:

1. The server reaches the Minecraft `Done` state.
2. Runtime identity reports `ZEROX Paper 1.21.11-v4`.
3. Runtime reports `preserve-semantics=true`.
4. Runtime reports TNT load shedding disabled.
5. The slow synchronous task is attributed and logged.
6. The repeating task still executes at its real cadence; it is not deferred.
7. No ZEROX plugin-task deferral message appears.
8. Async concurrency reaches at least two tasks through the bounded pool.
9. A moderate 64-TNT chain executes without ZEROX fuse deferral.
10. The server remains alive and shuts down cleanly.

The CI configuration deliberately includes old aggressive values:

```properties
behavior.preserve-semantics=true
plugins.defer-repeating-tasks=true
tnt.load-shedding-enabled=true
```

This proves the master semantic-preservation setting overrides stale v3 configuration.

## Safe plugin parallelism

ZEROX parallelizes only work that is already declared asynchronous by the plugin. The executor is bounded to prevent thread explosions and resource exhaustion.

Default production profile for six visible vCores:

```properties
behavior.preserve-semantics=true

plugins.sync-global-budget-ms=6
plugins.sync-per-plugin-budget-ms=3
plugins.sync-task-warning-ms=10
plugins.defer-repeating-tasks=false
plugins.log-overruns=true

plugins.async-core-threads=2
plugins.async-max-threads=4
plugins.async-queue-capacity=4096

tnt.load-shedding-enabled=false
```

Synchronous event listeners, commands, world mutation, inventory changes, combat and entity state remain on the authoritative server thread. ZEROX records slow scheduler tasks but does not alter their result or timing.

## What semantic preservation costs

A plugin that performs 30 ms of synchronous work still consumes 30 ms. ZEROX can identify it, but cannot make unsafe code parallel without changing behavior or introducing races.

Likewise, 30,000 real TNT explosions cannot be completed instantly while preserving exact fuse and event timing. v4 keeps those semantics. Administrators must reduce the workload, accept lag, or explicitly enable the optional timing-changing emergency mode.

## Production acceptance target

Use the real workload:

- CPU: AMD EPYC 7F72;
- six dedicated or pinned vCores;
- 16 GiB container memory;
- Java 21;
- 12 GiB matching `Xms` and `Xmx`;
- exact production plugin versions;
- production-world copy with pregenerated chunks;
- 60–80 players;
- 30-minute warm-up and at least 60 minutes measured.

Normal-load targets:

- median MSPT no more than 10 ms;
- p95 no more than 20 ms;
- p99 no more than 40 ms;
- TPS 20.0;
- no watchdog crashes, corruption or plugin compatibility failures.

These are acceptance targets, not unconditional guarantees.

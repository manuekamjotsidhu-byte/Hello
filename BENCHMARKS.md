# ZEROX Paper performance evidence

## User-observed v1 baseline

This is a field observation supplied from a Pterodactyl test server. It is not a controlled or independently reproduced benchmark.

Environment visible in the supplied log:

- Minecraft/Paper: 1.21.11
- Java: Temurin 25.0.3
- Maximum heap: 512 MiB
- Plugins initialized: 0
- Paper workers: 2
- Paper I/O workers: 1
- Netty threads: 4
- Online players during the test: 1

Before the large TNT chain:

- 10-second median MSPT: approximately 5.7–6.3 ms
- 10-second p95 MSPT: approximately 8.1–10.3 ms
- TPS: approximately 20.0

The player then created 30,870 TNT blocks. During the resulting chain reaction, reported one-minute TPS fell through:

`19.1, 17.6, 16.7, 16.0, 15.2, 14.4, 13.6, 11.9`

This demonstrates that the previous fork had good light-load performance but no effective explosion work budget.

## ZEROX v2 TNT acceptance test

GitHub Actions starts the real Paperclip jar on Java 21, force-loads a chunk, places and ignites 1,024 TNT blocks, requires the TNT limiter to defer work, requires the process to remain alive and performs a clean shutdown.

This proves that load shedding activates. It is not a production MSPT guarantee.

## ZEROX v3 plugin scheduler acceptance test

The v3 CI run additionally requires the real server to report the configured scheduler profile:

```text
[ZEROX] Plugin scheduler: sync=6ms global/3ms per plugin; async=2-8 threads, queue=4096.
```

The build also compiles the modified synchronous and asynchronous CraftScheduler implementations and embeds the exact generated source diff.

The CI smoke test validates installation and runtime configuration. A representative plugin-load benchmark still requires the production plugin set because plugin behavior differs substantially.

## Plugin-load protection model

ZEROX v3 separates plugin pressure into two classes:

### Asynchronous Bukkit tasks

Plugins that already call Bukkit's asynchronous scheduler execute in a bounded parallel executor. The default automatic sizing is based on visible processors and can be overridden in `.zerox/zerox.properties`.

### Synchronous repeating scheduler tasks

These tasks cannot safely execute in parallel when they access Bukkit, entities, chunks or plugin state. ZEROX measures them on the server thread. When a plugin exceeds the configured per-plugin budget, subsequent repeating executions are delayed while one-shot synchronous tasks continue to run.

Default profile:

```properties
plugins.sync-global-budget-ms=6
plugins.sync-per-plugin-budget-ms=3
plugins.sync-task-warning-ms=10
plugins.max-penalty-ticks=20
plugins.defer-repeating-tasks=true
plugins.log-overruns=true
plugins.async-core-threads=auto
plugins.async-max-threads=auto
plugins.async-queue-capacity=4096
```

This model reduces scheduler-driven tick storms. It cannot automatically parallelize event listeners such as movement, block, inventory or combat handlers because those handlers participate synchronously in the current event result.

## Production acceptance target

A meaningful production benchmark should use:

- CPU: AMD EPYC 7F72
- CPU allocation: 6 dedicated or pinned vCores
- Container memory: 16 GiB
- Java: 21
- Java heap: 12 GiB, matching Xms and Xmx
- Plugins: exact production set and versions
- World: a copy of the production world
- Chunks: pregenerated
- Players: 60–80 simulated or real
- Warm-up: at least 30 minutes
- Measured run: at least 60 minutes

Target under normal production load:

- Median MSPT: no more than 10 ms
- p95 MSPT: no more than 20 ms
- p99 MSPT: no more than 40 ms
- TPS: 20.0
- Watchdog crashes: 0
- Chunk corruption: 0
- Plugin compatibility failures: 0

Also record per-plugin scheduler warnings and spark profiles. Any plugin repeatedly producing 10+ ms synchronous tasks should be optimized or reconfigured; increasing the guard limits merely allows it to consume more of the tick.

These are acceptance targets, not unconditional guarantees. Huge synchronous world edits, synchronous plugin listeners, uncontrolled chunk generation or unbounded explosions can exceed them.

## TNT behavior tradeoff

Default strict profile:

```properties
tnt.max-explosions-per-tick=4
tnt.max-processing-ms-per-tick=3
```

More restrictive profile:

```properties
tnt.max-explosions-per-tick=2
tnt.max-processing-ms-per-tick=2
```

Faster-blast profile with greater lag risk:

```properties
tnt.max-explosions-per-tick=8
tnt.max-processing-ms-per-tick=5
```

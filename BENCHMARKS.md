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

## ZEROX v2 CI acceptance test

GitHub Actions performs an automated safety/load smoke test on Java 21:

1. Builds the fork from pinned Paper 1.21.11 build 132 source.
2. Starts the generated Paperclip jar with a 1 GiB heap on a small hosted runner.
3. Requires the server to reach the Minecraft `Done` state.
4. Requires runtime identity to contain `ZEROX Paper 1.21.11-v2`.
5. Force-loads the target chunk.
6. Places and ignites 1,024 TNT blocks.
7. Requires the ZEROX TNT load guard to defer explosion work.
8. Requires the server process to remain alive after the load.
9. Runs a TPS command and performs a clean console shutdown.

An earlier 8-explosion/5-ms test remained alive and reported 18.6 one-minute TPS shortly after ignition on the constrained CI runner. The production default was subsequently tightened to 4 explosions and 3 ms per tick. This test establishes build/startup integrity and confirms that load shedding activates; it is not a production MSPT service-level benchmark.

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

These are acceptance targets, not unconditional guarantees. Huge synchronous world edits, plugins, uncontrolled chunk generation, or unbounded explosions can exceed them.

## TNT behavior tradeoff

ZEROX v2 protects responsiveness by delaying excess explosions. For very large TNT chains:

- total blast completion time increases;
- individual explosions and Bukkit events remain on the server thread;
- fewer explosions are allowed to consume one tick;
- the limiter can be tuned in `.zerox/zerox.properties`.

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

Very fast blast processing, highest lag risk:

```properties
tnt.max-explosions-per-tick=16
tnt.max-processing-ms-per-tick=7
```

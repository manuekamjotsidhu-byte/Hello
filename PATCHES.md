# ZEROX Paper 1.21.11 v4.3 patch manifest

## Upstream identity

- Project: PaperMC/Paper
- Paper build: 132
- Minecraft: 1.21.11
- Upstream commit: `c5eb0790f199da6c38d0a650e1e5cd5415b28185`
- Java build target: 21

## ZEROX patch series

1. `0001-visible-build-identity.patch`
   - Visible ZEROX build and source identity.

2. `0002-safe-performance-defaults.patch`
   - Enables Paper's optimized explosion calculation.

3. `0003-adaptive-tnt-explosion-budget.patch`
   - Optional emergency TNT load shedding; disabled in semantic-preserving mode.

4. `0004-startup-runtime-profile.patch`
   - Startup timing plus bounded Paper worker and Netty configuration.

5. `0005-plugin-parallelism-load-guard.patch`
   - Bounded execution for plugin work already declared asynchronous.
   - Synchronous scheduler timing telemetry.

6. `0006-semantic-preserving-defaults.patch`
   - Events, commands, world mutation and plugin return values remain authoritative.
   - Plugin-task and TNT deferral are disabled by default.

7. `0007-restore-legacy-tnt-and-world-settings.patch`
   - Repairs exact older ZEROX values and creates backups.

8. `0008-progressive-player-join-load.patch`
   - Progressive post-join send-distance expansion.
   - Bounded asynchronous chunk loading, generation and sending.
   - Slow synchronous listener attribution.

9. `0009-high-density-backpressure.patch`
   - Removes `CallerRunsPolicy` from the asynchronous plugin executor.
   - Saturated async work is retained in an off-main overflow queue.
   - Adapts async concurrency using measured synchronous plugin pressure and MSPT.
   - Reserves CPU capacity for the authoritative server tick.
   - Pauses and later resumes join chunk expansion under pressure.
   - Uses denser per-player chunk admission values: send `24`, load `36`, generate `8`, concurrent load/generate `3/1`.
   - Does not automatically parallelize unsafe synchronous Bukkit work.

## V4.3 density defaults

```properties
behavior.preserve-semantics=true
plugins.defer-repeating-tasks=false
tnt.load-shedding-enabled=false

density.target-mspt=20
density.plugin-high-ms=12
density.plugin-critical-ms=18
density.join-hold-mspt=18
density.reserve-main-cores=2
density.async-overflow-queue=16384

plugins.async-core-threads=auto
plugins.async-max-threads=auto
plugins.async-queue-capacity=16384

join.progressive-view-distance=true
join.initial-send-distance=3
join.ramp-interval-ticks=8
join.start-grace-ticks=10
join.max-ramp-steps-per-tick=1
events.listener-warning-ms=10
```

## Configuration migration

V4.3 migrates only exact v4.2 admission values:

```text
player-max-chunk-send-rate: 35.0 -> 24.0
player-max-chunk-load-rate: 50.0 -> 36.0
player-max-chunk-generate-rate: 12.0 -> 8.0
player-max-concurrent-chunk-loads: 4 -> 3
player-max-concurrent-chunk-generates: 2 -> 1
```

The original file is backed up as `.zerox/backups/config_paper-global.yml.pre-v4.3.bak`. Custom values are retained.

## Claim boundary

The fork can prevent asynchronous saturation and join/chunk bursts from unnecessarily starving the main tick. It cannot safely move arbitrary synchronous listeners, commands, inventories, entity logic or world mutation to other threads.

Running 200–300 players on 8 GiB depends on CPU allocation, world state, view distance, entity count and the exact plugin set. A fixed sub-20 MSPT guarantee is not claimed without a production benchmark.

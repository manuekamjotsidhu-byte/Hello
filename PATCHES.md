# ZEROX Paper 1.21.11 v4.2 patch manifest

## Upstream identity

- Project: PaperMC/Paper
- Paper build: 132
- Minecraft: 1.21.11
- Upstream commit: `c5eb0790f199da6c38d0a650e1e5cd5415b28185`
- Java build target: 21

## ZEROX patch series

1. `0001-visible-build-identity.patch`
   - Identifies the implementation as `ZEROX Paper` and embeds build identity.

2. `0002-safe-performance-defaults.patch`
   - Enables Paper's optimized explosion calculation.

3. `0003-adaptive-tnt-explosion-budget.patch`
   - Optional emergency TNT load shedding; disabled in semantic-preserving mode.

4. `0004-startup-runtime-profile.patch`
   - Reports startup timing and configures bounded worker and Netty threads.

5. `0005-plugin-parallelism-load-guard.patch`
   - Uses a bounded executor only for tasks plugins already schedule asynchronously.
   - Measures synchronous scheduler work.

6. `0006-semantic-preserving-defaults.patch`
   - Keeps Bukkit events, commands, world mutation and plugin return values authoritative.
   - Disables task and TNT deferral by default.

7. `0007-restore-legacy-tnt-and-world-settings.patch`
   - Repairs exact v2/v3 persistent values and creates backups under `.zerox/backups/`.

8. `0008-progressive-player-join-load.patch`
   - Starts post-event player chunk delivery at send distance `3` and expands it one chunk every `8` ticks.
   - Uses Paper's existing asynchronous chunk loading, generation and I/O workers instead of performing chunk work on the main thread.
   - Bounds per-player chunk rates to `35` sends/s, `50` loads/s and `12` generations/s.
   - Caps per-player concurrency at `4` chunk loads and `2` chunk generations.
   - Finalizes at most one simultaneous join per tick.
   - Reports slow synchronous event listeners with plugin, event and listener class.
   - Does not cancel, skip, replace or silently defer player work.
   - Does not move arbitrary Bukkit listeners or world access off-thread.
   - Respects explicit plugin changes to per-player send distance.

## Default safety model

```properties
behavior.preserve-semantics=true
plugins.defer-repeating-tasks=false
tnt.load-shedding-enabled=false

join.progressive-view-distance=true
join.initial-send-distance=3
join.ramp-interval-ticks=8
join.start-grace-ticks=10
join.max-ramp-steps-per-tick=1
events.listener-warning-ms=15
```

Join work is queued and completed; it is not discarded. Only chunk operations already designed by Paper for concurrency use worker threads. Synchronous plugin event handlers remain on the server thread because their cancellation state, return values and world mutations are part of the current tick.

## Existing configuration migration

On first v4.2 startup, exact upstream values in `config/paper-global.yml` are migrated:

```text
player-max-chunk-send-rate: 75.0  -> 35.0
player-max-chunk-load-rate: 100.0 -> 50.0
player-max-chunk-generate-rate: -1.0 -> 12.0
player-max-concurrent-chunk-loads: 0 -> 4
player-max-concurrent-chunk-generates: 0 -> 2
max-joins-per-tick: 5 -> 1
```

Custom non-default administrator values are preserved. The original file is backed up as `.zerox/backups/config_paper-global.yml.pre-v4.2.bak`.

## Accurate claim

> Based on Paper 1.21.11 build 132 with semantic-preserving join-load smoothing, bounded asynchronous chunk/plugin work, synchronous event attribution, migration, startup and stability patches.

This release does not claim full multicore world ticking, guaranteed MSPT, or safe parallel execution of arbitrary synchronous plugins.

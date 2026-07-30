# ZEROX Paper 1.21.11 v3 patch manifest

## Upstream identity

- Project: PaperMC/Paper
- Paper build: 132
- Minecraft: 1.21.11
- Upstream commit: `c5eb0790f199da6c38d0a650e1e5cd5415b28185`
- Java build target: 21

## ZEROX patch series

1. `0001-visible-build-identity.patch`
   - Identifies the running implementation as `ZEROX Paper`.
   - Extends version output with the ZEROX release identifier.
   - Embeds `META-INF/zerox-build.json` in the executable Paperclip jar.

2. `0002-safe-performance-defaults.patch`
   - Disables armor-stand collision lookups by default.
   - Enables Paper's optimized explosion calculation by default.
   - Disables pathfinding recalculation on every block update by default.
   - Reduces the default primed-TNT entity tick ceiling from 100 to 16 per tick.

3. `0003-adaptive-tnt-explosion-budget.patch`
   - Adds a per-world explosion budget.
   - Defers excess primed-TNT explosions by resetting their fuse to one tick.
   - Defaults to 4 explosions and 3 milliseconds of explosion scheduling work per world tick.
   - Keeps every explosion on the authoritative server thread to preserve Paper/Bukkit event ordering.

4. `0004-startup-runtime-profile.patch`
   - Reports ZEROX startup timing.
   - Generates `.zerox/zerox.properties` for owned performance settings.
   - Selects conservative chunk-worker and Netty thread counts from visible processors.
   - Warns when Paper 1.21.11 is run outside Java 21 or with a very small heap.
   - Retains first-run web activation and stores only a derived activation token.

5. `0005-plugin-parallelism-load-guard.patch`
   - Replaces Paper's effectively unbounded async-plugin platform-thread executor with a bounded parallel executor.
   - Defaults to an automatically sized async pool with a bounded 4,096-task queue.
   - Measures every synchronous Bukkit scheduler task by plugin and task class.
   - Applies a 6 ms total synchronous scheduler budget and a 3 ms per-plugin budget per tick.
   - Defers only repeating synchronous scheduler tasks when a plugin accumulates scheduler debt.
   - Never moves Bukkit events, one-shot synchronous tasks, commands, entity changes or world mutations to worker threads.
   - Logs tasks taking at least 10 ms so the responsible plugin can be identified.

## Main-thread safety model

ZEROX v3 uses parallelism only where the plugin has already requested asynchronous execution. Arbitrary synchronous plugin listeners cannot be automatically moved to other threads because their return values, cancellation state and world access are part of the current server tick.

The load guard therefore protects the server thread by delaying over-budget repeating scheduler work. It does not skip event listeners or pretend unsafe world access is parallel-safe.

## Auditable build output

GitHub Actions publishes:

- `ZEROX-Paper-1.21.11-v3.jar`
- `ZEROX-Paper-1.21.11-v3.jar.sha256`
- `zerox-build.json`
- `zerox-paper-server.patch`
- `zerox-minecraft.patch`
- `BUGFIXES.yml`
- `BENCHMARKS.md`
- CI startup, scheduler-profile and TNT-guard logs

The executable jar contains this manifest, the claims manifest, benchmark record and all five review patches under `META-INF/zerox/`.

## Scope of claims

This release is accurately described as:

> Based on Paper 1.21.11 build 132 with selected ZEROX performance, bounded plugin parallelism, scheduler load protection, startup, activation and TNT load-protection patches.

It does not claim:

- every Paper or Minecraft bug is fixed;
- a fixed MSPT under arbitrary workloads;
- Folia-style regionized world ticking;
- arbitrary synchronous Bukkit events are parallelized;
- byte-for-byte reproducibility until independently verified.

Plugins can still block the server thread inside synchronous event listeners, commands, database calls or direct world scans. ZEROX reports those scheduler overruns, but plugin source changes are required to move such work safely to async execution.

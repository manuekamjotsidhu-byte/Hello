# ZEROX Paper 1.21.11 v4 patch manifest

## Upstream identity

- Project: PaperMC/Paper
- Paper build: 132
- Minecraft: 1.21.11
- Upstream commit: `c5eb0790f199da6c38d0a650e1e5cd5415b28185`
- Java build target: 21

## ZEROX patch series

1. `0001-visible-build-identity.patch`
   - Identifies the implementation as `ZEROX Paper`.
   - Embeds build and source identity in the executable jar.

2. `0002-safe-performance-defaults.patch`
   - Enables Paper's optimized explosion calculation.
   - Earlier v2 gameplay-changing defaults are superseded by patch 0006.

3. `0003-adaptive-tnt-explosion-budget.patch`
   - Provides an optional emergency TNT load-shedding mechanism.
   - It is disabled by default in v4 and cannot activate while semantic-preserving mode is enabled.

4. `0004-startup-runtime-profile.patch`
   - Reports startup timing.
   - Configures bounded worker and Netty thread counts.
   - Retains first-run activation without storing the plaintext key.

5. `0005-plugin-parallelism-load-guard.patch`
   - Replaces the effectively unbounded async-plugin platform-thread executor with a bounded parallel executor.
   - Measures synchronous Bukkit scheduler tasks by plugin, task ID and Java class.
   - Produces slow-task telemetry.
   - Contains an optional repeating-task load-shedding mode, disabled by patch 0006.

6. `0006-semantic-preserving-defaults.patch`
   - Makes `behavior.preserve-semantics=true` the authoritative default.
   - Never skips, replaces, cancels, reorders or delays synchronous plugin work.
   - Restores upstream armor-stand collision, pathfinding and primed-TNT timing defaults.
   - Disables TNT fuse deferral and scheduler task deferral.
   - Retains bounded parallelism only for tasks plugins already scheduled asynchronously.

## Default safety model

```properties
behavior.preserve-semantics=true
plugins.defer-repeating-tasks=false
tnt.load-shedding-enabled=false
```

The master semantic setting overrides old v3 values. Existing installations therefore preserve real behavior even when their previous configuration still contains aggressive deferral settings.

Parallel execution remains enabled only for:

- Bukkit tasks already submitted through asynchronous scheduler APIs;
- Paper chunk generation and worker operations;
- chunk I/O;
- Netty networking;
- other upstream Paper operations already designed for concurrency.

The following remain authoritative and synchronous:

- Bukkit event listeners and cancellation results;
- commands;
- inventory actions;
- combat and entity mutation;
- world and block mutation;
- AI, redstone and tick ordering;
- synchronous plugin return values.

## Optional emergency mode

Timing-changing load shedding requires an explicit opt-out from semantic preservation:

```properties
behavior.preserve-semantics=false
plugins.defer-repeating-tasks=true
tnt.load-shedding-enabled=true
```

This mode is not the production default because it changes when work occurs.

## Auditable build output

GitHub Actions publishes:

- `ZEROX-Paper-1.21.11-v4.jar`
- `ZEROX-Paper-1.21.11-v4.jar.sha256`
- `zerox-build.json`
- exact generated source diffs
- `PATCHES.md`, `BUGFIXES.yml` and `BENCHMARKS.md`
- CI evidence for slow-task telemetry, preserved sync execution and bounded async concurrency

## Accurate claim

> Based on Paper 1.21.11 build 132 with selected ZEROX semantic-preserving performance, bounded async-plugin parallelism, observability, startup and activation patches.

This release does not claim guaranteed MSPT, full multicore world ticking, or automatic thread-safety for synchronous plugins.

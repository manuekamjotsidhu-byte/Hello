# ZEROX Paper 1.21.11 v2 patch manifest

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
   - Reduces the default primed-TNT entity tick ceiling from 100 to 32 per tick.

3. `0003-adaptive-tnt-explosion-budget.patch`
   - Adds a per-world explosion budget.
   - Defers excess primed-TNT explosions by resetting their fuse to one tick.
   - Defaults to 16 explosions and 7 milliseconds of explosion scheduling work per world tick.
   - Keeps every explosion on the authoritative server thread to preserve Paper/Bukkit event ordering.
   - Large TNT chains therefore take longer to complete instead of blocking one enormous tick.

4. `0004-startup-runtime-profile.patch`
   - Reports ZEROX startup timing.
   - Generates `.zerox/zerox.properties` for owned performance settings.
   - Selects conservative chunk-worker and Netty thread counts from visible processors.
   - Warns when Paper 1.21.11 is run outside Java 21 or with a very small heap.
   - Retains first-run web activation and stores only a derived activation token.

## Auditable build output

GitHub Actions publishes:

- `ZEROX-Paper-1.21.11-v2.jar`
- `ZEROX-Paper-1.21.11-v2.jar.sha256`
- `zerox-build.json`
- `zerox-paper-server.patch`
- `zerox-minecraft.patch`
- `BUGFIXES.yml`
- `BENCHMARKS.md`
- CI startup and TNT-guard logs

The executable jar also contains this manifest, the bug-fix manifest, the benchmark record, and the four review patches under `META-INF/zerox/`.

## Scope of claims

This release is accurately described as:

> Based on Paper 1.21.11 build 132 with selected ZEROX performance, startup, activation, and load-protection patches.

It does not claim:

- every Paper or Minecraft bug is fixed;
- a fixed MSPT under arbitrary workloads;
- full multicore world ticking;
- byte-for-byte reproducibility until independently verified;
- instantaneous processing of unbounded TNT chains.

Normal Paper plugin loading remains enabled. Plugins can still dominate MSPT through synchronous event handlers, database calls, world scans, or other main-thread work.

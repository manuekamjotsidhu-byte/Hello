# ZEROX Paper 1.21.11 v4.1 patch manifest

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
   - Earlier behavior-changing defaults are superseded by patches 0006 and 0007.

3. `0003-adaptive-tnt-explosion-budget.patch`
   - Provides an optional emergency TNT load-shedding mechanism.
   - It cannot activate while semantic-preserving mode is enabled.

4. `0004-startup-runtime-profile.patch`
   - Reports startup timing and configures bounded worker and Netty thread counts.
   - Retains first-run activation without storing the plaintext key.

5. `0005-plugin-parallelism-load-guard.patch`
   - Uses a bounded executor for tasks plugins already schedule asynchronously.
   - Measures synchronous scheduler tasks and reports slow plugins.

6. `0006-semantic-preserving-defaults.patch`
   - Makes `behavior.preserve-semantics=true` authoritative.
   - Restores upstream source defaults and disables task/TNT deferral.

7. `0007-restore-legacy-tnt-and-world-settings.patch`
   - Fixes upgrades where v2/v3 persistent YAML still overrides restored source defaults.
   - Migrates exact ZEROX legacy values `max-tnt-per-tick: 16|32` to `100`.
   - Restores armor-stand collision lookup and pathfinding update values previously written as `false`.
   - Forces persistent semantic-mode settings to disable TNT and plugin-task deferral.
   - Backs up every changed file under `.zerox/backups/`.
   - Stores a one-time migration marker to avoid repeated edits.

## Default safety model

```properties
behavior.preserve-semantics=true
plugins.defer-repeating-tasks=false
tnt.load-shedding-enabled=false
```

Existing v2/v3 installations are repaired on first v4.1 startup. Unrelated administrator values are preserved; only exact legacy ZEROX values are migrated.

## Auditable build output

GitHub Actions publishes:

- `ZEROX-Paper-1.21.11-v4.1.jar`
- `ZEROX-Paper-1.21.11-v4.1.jar.sha256`
- exact generated source diffs
- build, patch, claims and benchmark manifests
- live migration, backup and TNT-completion evidence

## Accurate claim

> Based on Paper 1.21.11 build 132 with selected ZEROX semantic-preserving performance, bounded async-plugin parallelism, observability, migration, startup and activation patches.

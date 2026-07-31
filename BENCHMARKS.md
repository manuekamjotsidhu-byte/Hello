# ZEROX Paper performance evidence

## Observed baseline

The supplied Paper 1.21.11 test held roughly 20 TPS under light load with median MSPT around 5.7–7.4 ms. Large TNT work and player joins produced CPU and tick spikes. The production workload previously described uses an AMD EPYC 7F72, six pinned vCores and about 69 plugins.

## V4.3 high-density design

V4.3 focuses on preserving the authoritative tick while keeping queued work:

```text
target MSPT: 20
reserved CPU capacity: 2 visible cores
async overflow queue: 16384 tasks
player chunk send/load/generate rates: 24/36/8 per second
concurrent player chunk loads/generates: 3/1
maximum joins finalized per tick: 1
```

The Bukkit asynchronous scheduler no longer uses `CallerRunsPolicy`. When its primary queue is full, work is kept in an off-main overflow queue and returned to the worker executor as capacity becomes available.

Async concurrency is adaptive:

- normal pressure: use the configured worker allowance minus reserved main-thread cores;
- elevated MSPT or synchronous plugin time: reduce async concurrency;
- critical pressure: allow one async worker until the tick recovers.

Progressive join chunk expansion pauses while the pressure signal is high and resumes later. Requested chunks are not discarded.

## Safety boundary

Synchronous Bukkit listeners, commands, inventories, entity state and world mutation keep their existing execution semantics. A server cannot automatically move arbitrary synchronous plugin code to another thread without plugin-specific thread-safety guarantees.

## CI acceptance test

The v4.3 workflow must prove:

1. Paper build 132 source patches apply and compile on Java 21.
2. Runtime identity reports `ZEROX Paper 1.21.11-v4.3`.
3. `CallerRunsPolicy` is absent from the plugin async executor.
4. A synthetic async burst fills the primary queue and engages the overflow queue.
5. Every synthetic async task completes.
6. No synthetic async task reports execution on the primary server thread.
7. Parallel async execution reaches at least two tasks.
8. A repeated synchronous workload is preserved and contributes to pressure telemetry.
9. Exact v4.2 chunk admission values migrate to v4.3 values with a backup.
10. Existing semantic-preservation, TNT and join regressions continue passing.

## 200–300 player acceptance target

Target deployment requested by the operator:

- 8 GiB container memory;
- Java 21;
- approximately 6 GiB matching `Xms` and `Xmx`;
- pregenerated production world;
- exact production plugin set;
- 200–300 connected players;
- no skipped gameplay work.

A valid production test requires at least 30 minutes warm-up and 60 minutes measured load. Record median, p95 and p99 MSPT, CPU saturation, GC pauses, loaded chunks, ticking entities, packet rates, synchronous plugin warnings and database latency.

Desired service objective:

```text
median MSPT <= 10
p95 MSPT <= 20
p99 MSPT <= 40
TPS = 20.0 during normal load
```

The jar does not claim that 300 players on 8 GiB will always remain below 20 MSPT. That result depends on plugin behavior, CPU allocation, world activity, entities and view distance, and must be demonstrated with the production workload.

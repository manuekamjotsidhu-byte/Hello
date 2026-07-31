# ZEROX Paper performance evidence

## User-observed baseline

The supplied Pterodactyl test used Paper 1.21.11, Java 25 and a 512 MiB heap. Light load held approximately 20 TPS with median MSPT around 5.7–7.4 ms. Large real TNT work exceeded one tick and reduced TPS. A later production observation showed CPU reaching maximum when a player joined.

The join symptom can come from two different sources:

1. initial chunk loading, generation, lighting and sending;
2. synchronous plugin handlers such as `PlayerJoinEvent`, permission, scoreboard, placeholder, database or world-scan code.

The first category can use Paper's worker system. The second category cannot be blindly moved off-thread without breaking Bukkit semantics.

## ZEROX v4.2 join-load design

V4.2 reduces the initial join burst without dropping work:

```text
initial player send distance: 3 chunks
ramp interval: 8 ticks
ramp size: 1 chunk
start grace: 10 ticks
maximum ramp steps per server tick: 1
```

Paper chunk limits used by default:

```text
player chunk send rate: 35 chunks/second
player chunk load rate: 50 chunks/second
player chunk generation rate: 12 chunks/second
concurrent loads per player: 4
concurrent generations per player: 2
maximum joins finalized per tick: 1
```

The server continues completing requested chunks. It feeds them gradually into Paper's existing asynchronous chunk loading, generation and I/O paths instead of creating a large join-time burst.

## Synchronous plugin event attribution

Every synchronous Bukkit listener is timed. A listener taking at least 15 ms produces an attributed warning containing:

- plugin name;
- event name;
- listener class;
- elapsed milliseconds.

The listener remains on the main thread because event cancellation, return values, inventory/world mutation and plugin ordering are authoritative. V4.2 does not pretend unsafe code is parallel.

## CI acceptance test

GitHub Actions builds the fork from pinned Paper build 132 source and starts the real Paperclip jar on Java 21.

The v4.2 regression test starts with exact upstream `paper-global.yml` values and passes only when:

1. The server reaches the Minecraft `Done` state.
2. Runtime identity reports `ZEROX Paper 1.21.11-v4.2`.
3. The join-load controller reports its enabled configuration.
4. Exact upstream chunk/join defaults are migrated to the bounded v4.2 values.
5. The original `paper-global.yml` is backed up.
6. Custom ZEROX join settings are persisted in `.zerox/zerox.properties`.
7. A synthetic synchronous event listener deliberately taking over 15 ms is attributed in the server log.
8. The event still executes normally; it is not skipped or moved off-thread.
9. Existing semantic-preservation and TNT regression tests continue to pass.
10. The server remains alive and shuts down cleanly.

## Production acceptance target

Target environment:

- AMD EPYC 7F72;
- six dedicated or pinned vCores;
- 16 GiB container memory;
- Java 21;
- 12 GiB matching `Xms` and `Xmx`;
- exact production plugin versions;
- production-world copy with pregenerated chunks;
- 60–80 players.

Measure joins into both pregenerated and ungenerated areas. Record:

- CPU peak and duration during join;
- main-thread MSPT p50/p95/p99;
- chunk worker CPU utilization;
- time until configured send distance is restored;
- slow listener warnings during `PlayerJoinEvent`;
- TPS during single and simultaneous joins.

Normal-load targets remain:

- median MSPT no more than 10 ms;
- p95 no more than 20 ms;
- p99 no more than 40 ms;
- TPS 20.0;
- no watchdog crashes, corruption or plugin compatibility failures.

These are acceptance targets, not unconditional guarantees.

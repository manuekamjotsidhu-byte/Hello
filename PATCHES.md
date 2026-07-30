# ZEROX Paper 1.21.11 patch manifest

Upstream: PaperMC/Paper commit `6da8af7ca4e29f4ea6961905a96d9f244980c932`.

## Source patches

1. First-run activation integrated into `net.minecraft.server.Main` before Paper binds the Minecraft port.
2. License verification stores only a derived SHA-256 activation token in `.zerox/activation.properties`; the plaintext key is not written.
3. Armor stand collision entity lookups default to disabled.
4. Optimized explosion processing defaults to enabled when the upstream field is present.
5. Pathfinding recalculation on block updates defaults to disabled when the upstream field is present.
6. Embedded build identity is written to `.zerox/build.properties`.

## Scope and claims

This is a source-built Paper fork. It does not claim that every Paper bug is patched or that MSPT is guaranteed under arbitrary workloads. The performance changes are conservative defaults intended to reduce common entity, explosion, and pathfinding overhead while preserving Paper plugin loading.

#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()


def replace(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected expression for {description} not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


limiter = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxExplosionLimiter.java"
replace(limiter, "level.dimension().location()", "level.dimension()", "1.21.11 world key")
replace(
    limiter,
    'Integer.getInteger("zerox.tnt.max-explosions-per-tick", 16)',
    'Integer.getInteger("zerox.tnt.max-explosions-per-tick", 4)',
    "default TNT explosion count budget",
)
replace(
    limiter,
    'Integer.getInteger("zerox.tnt.max-processing-ms-per-tick", 7)',
    'Integer.getInteger("zerox.tnt.max-processing-ms-per-tick", 3)',
    "default TNT time budget",
)

bootstrap = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java"
for old, new, description in (
    ('settings.setProperty("tnt.max-explosions-per-tick", "16");', 'settings.setProperty("tnt.max-explosions-per-tick", "4");', "generated TNT count setting"),
    ('settings.setProperty("tnt.max-processing-ms-per-tick", "7");', 'settings.setProperty("tnt.max-processing-ms-per-tick", "3");', "generated TNT time setting"),
    ('settings.getProperty("tnt.max-explosions-per-tick", "16")', 'settings.getProperty("tnt.max-explosions-per-tick", "4")', "TNT count fallback"),
    ('settings.getProperty("tnt.max-processing-ms-per-tick", "7")', 'settings.getProperty("tnt.max-processing-ms-per-tick", "3")', "TNT time fallback"),
):
    replace(bootstrap, old, new, description)

spigot = root / "paper-server/src/main/java/org/spigotmc/SpigotWorldConfig.java"
replace(
    spigot,
    'this.maxTntTicksPerTick = this.getInt("max-tnt-per-tick", 32);',
    'this.maxTntTicksPerTick = this.getInt("max-tnt-per-tick", 16);',
    "primed TNT tick ceiling",
)

build_info = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java"
replace(
    build_info,
    'return NAME + " " + VERSION + " (MC " + MINECRAFT_VERSION',
    'return NAME + " " + MINECRAFT_VERSION + "-v2 / " + VERSION + " (MC " + MINECRAFT_VERSION',
    "visible v2 identity",
)

print("Adjusted ZEROX Paper 1.21.11 mappings, identity, and strict TNT defaults")

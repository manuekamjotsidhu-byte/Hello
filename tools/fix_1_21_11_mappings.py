#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()

limiter = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxExplosionLimiter.java"
text = limiter.read_text(encoding="utf-8")
old = "level.dimension().location()"
new = "level.dimension()"
if old not in text:
    raise SystemExit(f"Expected 1.21.11 mapping expression not found in {limiter}")
limiter.write_text(text.replace(old, new, 1), encoding="utf-8")

build_info = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java"
text = build_info.read_text(encoding="utf-8")
old = 'return NAME + " " + VERSION + " (MC " + MINECRAFT_VERSION'
new = 'return NAME + " " + MINECRAFT_VERSION + "-v2 / " + VERSION + " (MC " + MINECRAFT_VERSION'
if old not in text:
    raise SystemExit(f"Expected ZEROX build identity expression not found in {build_info}")
build_info.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Adjusted ZEROX Paper 1.21.11 mappings and visible v2 identity")

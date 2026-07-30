#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxExplosionLimiter.java"
text = path.read_text(encoding="utf-8")
old = "level.dimension().location()"
new = "level.dimension()"
if old not in text:
    raise SystemExit(f"Expected 1.21.11 mapping expression not found in {path}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Adjusted ZEROX world-key logging for Paper 1.21.11 mappings")

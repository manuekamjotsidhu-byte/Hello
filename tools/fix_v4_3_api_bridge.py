#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
repo = Path(__file__).resolve().parent.parent

registered = root / "paper-api/src/main/java/org/bukkit/plugin/RegisteredListener.java"
server_pressure = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxMainThreadPressure.java"
api_target = root / "paper-api/src/main/java/io/papermc/paper/zerox/ZeroxApiPressure.java"
api_template = repo / "templates/v4_3/ZeroxApiPressure.java"

for path in (registered, server_pressure, api_template):
    if not path.is_file():
        raise SystemExit(f"Required bridge file missing: {path}")

text = registered.read_text(encoding="utf-8")
old = "io.papermc.paper.zerox.ZeroxMainThreadPressure.recordSyncWork(elapsedNanos);"
new = "io.papermc.paper.zerox.ZeroxApiPressure.recordSyncEvent(elapsedNanos);"
if new not in text:
    if old not in text:
        raise SystemExit("RegisteredListener pressure bridge patch point missing")
    registered.write_text(text.replace(old, new, 1), encoding="utf-8")

text = server_pressure.read_text(encoding="utf-8")
old = "        previousSyncNanos = currentSyncNanos;\n"
new = "        currentSyncNanos += ZeroxApiPressure.drainSyncEventNanos();\n        previousSyncNanos = currentSyncNanos;\n"
if new not in text:
    if old not in text:
        raise SystemExit("Server pressure drain patch point missing")
    server_pressure.write_text(text.replace(old, new, 1), encoding="utf-8")

api_target.parent.mkdir(parents=True, exist_ok=True)
api_target.write_text(api_template.read_text(encoding="utf-8"), encoding="utf-8")
print("ZEROX v4.3 API pressure bridge fixed")

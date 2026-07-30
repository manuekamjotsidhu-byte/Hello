#!/usr/bin/env python3
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()


def replace(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected expression for {description} not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


build_info = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java"
replace(build_info, 'public static final String VERSION = "2.0.0";', 'public static final String VERSION = "2.1.0";', "v3 version")
replace(build_info, 'public static final int PATCH_COUNT = 4;', 'public static final int PATCH_COUNT = 5;', "v3 patch count")
replace(build_info, 'MINECRAFT_VERSION + "-v2 / "', 'MINECRAFT_VERSION + "-v3 / "', "visible v3 identity")

bootstrap = root / "paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java"
replace(bootstrap, 'profileVersion=2\\n",', 'profileVersion=3\\n",', "profile version")
replace(bootstrap, 'ZEROX Paper performance profile v2', 'ZEROX Paper performance profile v3', "profile comment")

metadata_path = root / "paper-server/src/main/resources/META-INF/zerox-build.json"
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata.update({
    "version": "2.1.0",
    "patchCount": 5,
    "pluginAsyncParallelism": "bounded",
    "pluginSyncLoadGuard": True,
    "arbitrarySyncPluginEventsParallelized": False,
})
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

print("Finalized ZEROX Paper v3 metadata")

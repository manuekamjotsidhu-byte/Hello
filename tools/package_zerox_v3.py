#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

FIXED_TIMESTAMP = (2026, 7, 30, 0, 0, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed ZEROX v3 audit metadata into a Paperclip jar")
    parser.add_argument("jar", type=Path)
    parser.add_argument("--upstream-commit", required=True)
    parser.add_argument("--zerox-commit", required=True)
    parser.add_argument("--build-number", required=True)
    parser.add_argument("--build-time", required=True)
    return parser.parse_args()


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def add_text(archive: zipfile.ZipFile, name: str, text: str) -> None:
    archive.writestr(zip_info(name), text.encode("utf-8"))


def main() -> None:
    args = parse_args()
    jar = args.jar.resolve()
    if not jar.is_file():
        raise SystemExit(f"Jar not found: {jar}")

    repo = Path(__file__).resolve().parent.parent
    required_files = {
        "META-INF/zerox/PATCHES.md": repo / "PATCHES.md",
        "META-INF/zerox/BUGFIXES.yml": repo / "BUGFIXES.yml",
        "META-INF/zerox/BENCHMARKS.md": repo / "BENCHMARKS.md",
    }
    patch_dir = repo / "patches" / "server"
    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        raise SystemExit(f"No audit patches found in {patch_dir}")
    for archive_name, path in required_files.items():
        if not path.is_file():
            raise SystemExit(f"Required audit file missing: {path}")

    source_sha256 = hashlib.sha256(jar.read_bytes()).hexdigest()
    metadata = {
        "name": "ZEROX Paper",
        "version": "2.1.0",
        "minecraftVersion": "1.21.11",
        "upstreamPaperBuild": 132,
        "upstreamCommit": args.upstream_commit,
        "zeroxCommit": args.zerox_commit,
        "buildNumber": args.build_number,
        "buildTime": args.build_time,
        "patchCount": len(patches),
        "sourceRepository": "https://github.com/manuekamjotsidhu-byte/Hello",
        "javaTarget": 21,
        "paperPluginLoading": True,
        "pluginAsyncParallelism": "bounded",
        "pluginSyncLoadGuard": True,
        "arbitrarySyncPluginEventsParallelized": False,
        "fullMulticoreTicking": False,
        "fixedMsptGuarantee": False,
        "reproducible": False,
        "reproducibilityNote": "Inputs are pinned and CI is repeatable; byte-for-byte reproducibility has not been independently established.",
        "preAuditPaperclipSha256": source_sha256,
    }

    injected_names = {
        "META-INF/zerox-build.json",
        *required_files.keys(),
        *(f"META-INF/zerox/patches/{path.name}" for path in patches),
    }

    with tempfile.NamedTemporaryFile(prefix="zerox-paper-v3-", suffix=".jar", delete=False, dir=jar.parent) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with zipfile.ZipFile(jar, "r") as source, zipfile.ZipFile(
            temporary_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            allowZip64=True,
        ) as target:
            seen: set[str] = set()
            for item in source.infolist():
                if item.filename in injected_names:
                    continue
                if item.filename in seen:
                    raise SystemExit(f"Duplicate entry in source jar: {item.filename}")
                seen.add(item.filename)
                target.writestr(item, source.read(item.filename))

            add_text(target, "META-INF/zerox-build.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            for archive_name, path in required_files.items():
                add_text(target, archive_name, path.read_text(encoding="utf-8"))
            for path in patches:
                add_text(target, f"META-INF/zerox/patches/{path.name}", path.read_text(encoding="utf-8"))

        with zipfile.ZipFile(temporary_path, "r") as check:
            names = check.namelist()
            if len(names) != len(set(names)):
                raise SystemExit("Packaged jar contains duplicate ZIP entries")
            for required in injected_names:
                if required not in names:
                    raise SystemExit(f"Packaged jar is missing {required}")
            bad = check.testzip()
            if bad is not None:
                raise SystemExit(f"Archive integrity failed at {bad}")

        temporary_path.replace(jar)
        print(f"Packaged {jar.name} with {len(patches)} auditable ZEROX patches")
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

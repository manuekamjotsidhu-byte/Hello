#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()


def require(path: str) -> Path:
    target = root / path
    if not target.is_file():
        raise SystemExit(f"Required file not found: {target}")
    return target


def replace_once(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch point missing for {description}: {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


bootstrap = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBootstrap.java")
replace_once(
    bootstrap,
    "import java.nio.file.Path;\n",
    "import java.nio.file.Path;\nimport java.nio.file.StandardCopyOption;\n",
    "migration backup import",
)
replace_once(
    bootstrap,
    "        final int processors = Runtime.getRuntime().availableProcessors();\n",
    "        migrateLegacyGameplaySettings(settings);\n\n        final int processors = Runtime.getRuntime().availableProcessors();\n",
    "legacy gameplay migration invocation",
)
replace_once(
    bootstrap,
    "    private static void printRuntimeWarnings() {\n",
    r'''    private static void migrateLegacyGameplaySettings(final Properties settings) throws IOException {
        final boolean preserveSemantics = Boolean.parseBoolean(
            settings.getProperty("behavior.preserve-semantics", "true")
        );
        if (!preserveSemantics) {
            return;
        }

        settings.setProperty("behavior.preserve-semantics", "true");
        settings.setProperty("tnt.load-shedding-enabled", "false");
        settings.setProperty("plugins.defer-repeating-tasks", "false");

        if (!Boolean.parseBoolean(settings.getProperty("migration.v4-1-gameplay-restored", "false"))) {
            boolean restored = false;
            restored |= migrateYamlScalar(Path.of("spigot.yml"), "max-tnt-per-tick", new String[]{"16", "32"}, "100");
            restored |= migrateYamlScalar(Path.of("config", "paper-world-defaults.yml"), "do-collision-entity-lookups", new String[]{"false"}, "true");
            restored |= migrateYamlScalar(Path.of("config", "paper-world-defaults.yml"), "update-pathfinding-on-block-update", new String[]{"false"}, "true");
            settings.setProperty("migration.v4-1-gameplay-restored", "true");
            if (restored) {
                System.out.println("[ZEROX] Restored legacy v2/v3 gameplay limits; TNT and world behavior now use Paper-compatible values.");
            }
        }

        try (var out = Files.newOutputStream(SETTINGS)) {
            settings.store(out, "ZEROX Paper v4.1 semantic-preserving profile");
        }
    }

    private static boolean migrateYamlScalar(
        final Path file,
        final String key,
        final String[] legacyValues,
        final String replacement
    ) throws IOException {
        if (!Files.isRegularFile(file)) {
            return false;
        }
        final java.util.List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        boolean changed = false;
        for (int index = 0; index < lines.size(); ++index) {
            final String line = lines.get(index);
            final int colon = line.indexOf(':');
            if (colon < 0 || !line.substring(0, colon).trim().equals(key)) {
                continue;
            }
            final String remainder = line.substring(colon + 1);
            final int commentIndex = remainder.indexOf('#');
            final String scalar = (commentIndex >= 0 ? remainder.substring(0, commentIndex) : remainder).trim();
            boolean legacy = false;
            for (String legacyValue : legacyValues) {
                if (scalar.equals(legacyValue)) {
                    legacy = true;
                    break;
                }
            }
            if (!legacy) {
                continue;
            }
            final String comment = commentIndex >= 0 ? " " + remainder.substring(commentIndex).trim() : "";
            lines.set(index, line.substring(0, colon + 1) + " " + replacement + comment);
            changed = true;
        }
        if (!changed) {
            return false;
        }

        final Path backupDir = DIR.resolve("backups");
        Files.createDirectories(backupDir);
        final String backupName = file.toString().replace('/', '_').replace('\\', '_') + ".pre-v4.1.bak";
        Files.copy(file, backupDir.resolve(backupName), StandardCopyOption.REPLACE_EXISTING);
        Files.write(file, lines, StandardCharsets.UTF_8);
        System.out.println("[ZEROX] Migrated legacy setting '" + key + "' in " + file
            + "; backup=" + backupDir.resolve(backupName) + ".");
        return true;
    }

    private static void printRuntimeWarnings() {
''',
    "legacy gameplay migration implementation",
)

build_info = require("paper-server/src/main/java/io/papermc/paper/zerox/ZeroxBuildInfo.java")
replace_once(build_info, 'public static final String VERSION = "2.2.0";', 'public static final String VERSION = "2.2.1";', "v4.1 version")
replace_once(build_info, 'public static final int PATCH_COUNT = 6;', 'public static final int PATCH_COUNT = 7;', "v4.1 patch count")
replace_once(build_info, 'MINECRAFT_VERSION + "-v4 / "', 'MINECRAFT_VERSION + "-v4.1 / "', "visible v4.1 identity")

craft_server = require("paper-server/src/main/java/org/bukkit/craftbukkit/CraftServer.java")
replace_once(craft_server, "ZEROX Paper 1.21.11-v4", "ZEROX Paper 1.21.11-v4.1", "CraftServer v4.1 identity")

metadata_path = require("paper-server/src/main/resources/META-INF/zerox-build.json")
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
metadata.update({
    "version": "2.2.1",
    "patchCount": 7,
    "legacyGameplayMigration": True,
    "legacyTntLimitsRestored": [16, 32, 100],
    "migrationBackups": ".zerox/backups",
})
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

print("ZEROX v4.1 legacy gameplay migration applied to", root)

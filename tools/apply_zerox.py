#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

UPSTREAM_COMMIT = "c5eb0790f199da6c38d0a650e1e5cd5415b28185"
MC_VERSION = "1.21.11"
ZEROX_VERSION = "2.0.0"

root = Path(sys.argv[1]).resolve()
zerox_commit = os.getenv("ZEROX_COMMIT", "development")
build_number = os.getenv("ZEROX_BUILD_NUMBER", "local")
build_time = os.getenv("ZEROX_BUILD_TIME", "unknown")


def require_file(*relative_candidates: str) -> Path:
    for candidate in relative_candidates:
        path = root / candidate
        if path.is_file():
            return path
    joined = ", ".join(relative_candidates)
    raise SystemExit(f"Required source file not found: {joined}")


def replace_once(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch point missing for {description}: {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


main = require_file(
    "paper-server/src/minecraft/java/net/minecraft/server/Main.java",
    "paper-server/src/minecraft/net/minecraft/server/Main.java",
)
replace_once(
    main,
    "SharedConstants.tryDetectVersion();",
    "SharedConstants.tryDetectVersion();\n"
    "        io.papermc.paper.zerox.ZeroxBootstrap.activateAndPrepare(); // ZEROX",
    "bootstrap activation and runtime profile",
)

minecraft_server = require_file(
    "paper-server/src/minecraft/java/net/minecraft/server/MinecraftServer.java",
    "paper-server/src/minecraft/net/minecraft/server/MinecraftServer.java",
)
replace_once(
    minecraft_server,
    'LOGGER.info("Done ({})! For help, type \\"help\\"", String.format(java.util.Locale.ROOT, "%.3fs", actualDoneTimeMs / 1000.00D)); // Paper - Improve startup message',
    'LOGGER.info("Done ({})! For help, type \\"help\\"", String.format(java.util.Locale.ROOT, "%.3fs", actualDoneTimeMs / 1000.00D)); // Paper - Improve startup message\n'
    "            io.papermc.paper.zerox.ZeroxBootstrap.reportReady(actualDoneTimeMs); // ZEROX",
    "startup timing report",
)

craft_server = require_file("paper-server/src/main/java/org/bukkit/craftbukkit/CraftServer.java")
replace_once(
    craft_server,
    "private final String serverName = io.papermc.paper.ServerBuildInfo.buildInfo().brandName();",
    'private final String serverName = "ZEROX Paper"; // ZEROX',
    "visible ZEROX server name",
)
replace_once(
    craft_server,
    'return this.serverVersion + " (MC: " + this.console.getServerVersion() + ")";',
    'return this.serverVersion + " / ZEROX Paper 1.21.11-v2 (MC: " + this.console.getServerVersion() + ")"; // ZEROX',
    "visible ZEROX version output",
)

world = require_file("paper-server/src/main/java/io/papermc/paper/configuration/WorldConfiguration.java")
for old, new, description in (
    (
        "public boolean doCollisionEntityLookups = true;",
        "public boolean doCollisionEntityLookups = false; // ZEROX: avoid unnecessary armor-stand collision scans",
        "armor stand collision lookup default",
    ),
    (
        "public boolean optimizeExplosions = false;",
        "public boolean optimizeExplosions = true; // ZEROX: optimized explosion block-density calculation",
        "optimized explosions default",
    ),
    (
        "public boolean updatePathfindingOnBlockUpdate = true;",
        "public boolean updatePathfindingOnBlockUpdate = false; // ZEROX: avoid pathfinding recalculation storms",
        "pathfinding update default",
    ),
):
    replace_once(world, old, new, description)

spigot_world = require_file("paper-server/src/main/java/org/spigotmc/SpigotWorldConfig.java")
replace_once(
    spigot_world,
    'this.maxTntTicksPerTick = this.getInt("max-tnt-per-tick", 100);',
    'this.maxTntTicksPerTick = this.getInt("max-tnt-per-tick", 32); // ZEROX: bound TNT entity work per tick',
    "TNT tick default",
)

primed_tnt = require_file(
    "paper-server/src/minecraft/java/net/minecraft/world/entity/item/PrimedTnt.java",
    "paper-server/src/minecraft/net/minecraft/world/entity/item/PrimedTnt.java",
)
replace_once(
    primed_tnt,
    '''        if (i <= 0) {
            // CraftBukkit start - Need to reverse the order of the explosion and the entity death so we have a location for the event''',
    '''        if (i <= 0) {
            // ZEROX start - spread extreme TNT chains across ticks to protect the main tick loop
            if (this.level() instanceof ServerLevel serverLevel && !io.papermc.paper.zerox.ZeroxExplosionLimiter.tryAcquire(serverLevel)) {
                this.setFuse(1);
                return;
            }
            // ZEROX end
            // CraftBukkit start - Need to reverse the order of the explosion and the entity death so we have a location for the event''',
    "TNT explosion budget",
)

pkg = root / "paper-server/src/main/java/io/papermc/paper/zerox"
pkg.mkdir(parents=True, exist_ok=True)

build_info_java = f'''package io.papermc.paper.zerox;

public final class ZeroxBuildInfo {{
    public static final String NAME = "ZEROX Paper";
    public static final String VERSION = "{ZEROX_VERSION}";
    public static final String MINECRAFT_VERSION = "{MC_VERSION}";
    public static final String UPSTREAM_COMMIT = "{UPSTREAM_COMMIT}";
    public static final String ZEROX_COMMIT = "{zerox_commit}";
    public static final String BUILD_NUMBER = "{build_number}";
    public static final String BUILD_TIME = "{build_time}";
    public static final int PATCH_COUNT = 4;

    private ZeroxBuildInfo() {{}}

    public static String summary() {{
        return NAME + " " + VERSION + " (MC " + MINECRAFT_VERSION
            + ", upstream " + UPSTREAM_COMMIT.substring(0, 7)
            + ", ZEROX " + ZEROX_COMMIT.substring(0, Math.min(7, ZEROX_COMMIT.length())) + ")";
    }}
}}
'''
(pkg / "ZeroxBuildInfo.java").write_text(build_info_java, encoding="utf-8")

(pkg / "ZeroxExplosionLimiter.java").write_text(r'''package io.papermc.paper.zerox;

import java.util.Map;
import java.util.WeakHashMap;
import java.util.concurrent.TimeUnit;
import net.minecraft.server.level.ServerLevel;

public final class ZeroxExplosionLimiter {
    private static final Map<ServerLevel, Budget> BUDGETS = new WeakHashMap<>();
    private static final int MAX_EXPLOSIONS_PER_TICK = clamp(
        Integer.getInteger("zerox.tnt.max-explosions-per-tick", 16), 1, 4096
    );
    private static final long MAX_PROCESSING_NANOS = TimeUnit.MILLISECONDS.toNanos(clamp(
        Integer.getInteger("zerox.tnt.max-processing-ms-per-tick", 7), 1, 45
    ));
    private static final boolean LOG_DEFERRALS = Boolean.parseBoolean(
        System.getProperty("zerox.tnt.log-deferrals", "true")
    );

    private ZeroxExplosionLimiter() {}

    public static synchronized boolean tryAcquire(final ServerLevel level) {
        final long tick = level.getGameTime();
        final long now = System.nanoTime();
        final Budget budget = BUDGETS.computeIfAbsent(level, ignored -> new Budget());

        if (budget.tick != tick) {
            budget.tick = tick;
            budget.startedNanos = now;
            budget.explosions = 0;
        }

        if (budget.explosions >= MAX_EXPLOSIONS_PER_TICK || now - budget.startedNanos >= MAX_PROCESSING_NANOS) {
            budget.deferred++;
            if (LOG_DEFERRALS && (budget.lastLogNanos == 0L || now - budget.lastLogNanos >= TimeUnit.SECONDS.toNanos(5))) {
                System.out.println("[ZEROX] TNT load guard deferred " + budget.deferred
                    + " explosion(s) in world " + level.dimension().location()
                    + "; budget=" + MAX_EXPLOSIONS_PER_TICK + " explosions/"
                    + TimeUnit.NANOSECONDS.toMillis(MAX_PROCESSING_NANOS) + "ms per tick.");
                budget.lastLogNanos = now;
                budget.deferred = 0L;
            }
            return false;
        }

        budget.explosions++;
        return true;
    }

    public static int maxExplosionsPerTick() {
        return MAX_EXPLOSIONS_PER_TICK;
    }

    public static long maxProcessingMillisPerTick() {
        return TimeUnit.NANOSECONDS.toMillis(MAX_PROCESSING_NANOS);
    }

    private static int clamp(final int value, final int minimum, final int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private static final class Budget {
        private long tick = Long.MIN_VALUE;
        private long startedNanos;
        private int explosions;
        private long deferred;
        private long lastLogNanos;
    }
}
''', encoding="utf-8")

(pkg / "ZeroxBootstrap.java").write_text(r'''package io.papermc.paper.zerox;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;

public final class ZeroxBootstrap {
    private static final String EXPECTED_KEY_SHA256 = "f584e637e37772eaa684ad6dcfa49858206c02ab68217c69579204600239660b";
    private static final Path DIR = Path.of(".zerox");
    private static final Path ACTIVATION = DIR.resolve("activation.properties");
    private static final Path SETTINGS = DIR.resolve("zerox.properties");
    private static final long START_NANOS = System.nanoTime();

    private ZeroxBootstrap() {}

    public static void activateAndPrepare() {
        try {
            Files.createDirectories(DIR);
            applyRuntimeProfile();
            final int port = detectPort();
            final String fingerprint = fingerprint(port);
            if (!validActivation(fingerprint)) {
                runActivationServer(port, fingerprint);
            }
            writeBuildMetadata();
            printRuntimeWarnings();
            System.out.println("[ZEROX] License verified. Starting " + ZeroxBuildInfo.summary() + ".");
        } catch (Exception ex) {
            throw new IllegalStateException("ZEROX activation failed", ex);
        }
    }

    public static void reportReady(final long paperStartupMillis) {
        final long zeroxStartupMillis = (System.nanoTime() - START_NANOS) / 1_000_000L;
        System.out.println("[ZEROX] Ready in " + paperStartupMillis + "ms (ZEROX bootstrap clock "
            + zeroxStartupMillis + "ms); TNT budget="
            + ZeroxExplosionLimiter.maxExplosionsPerTick() + " explosions/"
            + ZeroxExplosionLimiter.maxProcessingMillisPerTick() + "ms per tick.");
    }

    private static void applyRuntimeProfile() throws IOException {
        final Properties settings = new Properties();
        if (Files.isRegularFile(SETTINGS)) {
            try (var in = Files.newInputStream(SETTINGS)) {
                settings.load(in);
            }
        } else {
            settings.setProperty("worker-threads", "auto");
            settings.setProperty("tnt.max-explosions-per-tick", "16");
            settings.setProperty("tnt.max-processing-ms-per-tick", "7");
            settings.setProperty("tnt.log-deferrals", "true");
            try (var out = Files.newOutputStream(SETTINGS)) {
                settings.store(out, "ZEROX Paper performance profile v2");
            }
        }

        final int processors = Runtime.getRuntime().availableProcessors();
        final String configuredWorkers = settings.getProperty("worker-threads", "auto").trim();
        final int workers = configuredWorkers.equalsIgnoreCase("auto")
            ? Math.max(2, Math.min(4, processors / 2))
            : clamp(parseInt(configuredWorkers, 2), 1, Math.max(1, processors - 1));

        setDefaultSystemProperty("Paper.WorkerThreadCount", Integer.toString(workers));
        setDefaultSystemProperty("io.netty.eventLoopThreads", Integer.toString(Math.max(2, Math.min(4, processors / 2))));
        setDefaultSystemProperty("io.netty.allocator.maxOrder", "9");
        setDefaultSystemProperty("zerox.tnt.max-explosions-per-tick", settings.getProperty("tnt.max-explosions-per-tick", "16"));
        setDefaultSystemProperty("zerox.tnt.max-processing-ms-per-tick", settings.getProperty("tnt.max-processing-ms-per-tick", "7"));
        setDefaultSystemProperty("zerox.tnt.log-deferrals", settings.getProperty("tnt.log-deferrals", "true"));

        System.out.println("[ZEROX] Runtime profile: CPUs=" + processors + ", chunk-workers="
            + System.getProperty("Paper.WorkerThreadCount") + ", netty="
            + System.getProperty("io.netty.eventLoopThreads") + ".");
    }

    private static void printRuntimeWarnings() {
        final int feature = Runtime.version().feature();
        final long maxHeapMiB = Runtime.getRuntime().maxMemory() / 1024L / 1024L;
        if (feature != 21) {
            System.out.println("[ZEROX] WARNING: Paper 1.21.11 is tested on Java 21; detected Java " + feature + ".");
        }
        if (maxHeapMiB < 2048L) {
            System.out.println("[ZEROX] WARNING: Maximum heap is only " + maxHeapMiB
                + " MiB. Use matching -Xms/-Xmx; 12G is recommended for a 16G container.");
        }
    }

    private static int detectPort() throws IOException {
        for (String name : new String[]{"SERVER_PORT", "PORT", "P_SERVER_PORT"}) {
            final String value = System.getenv(name);
            if (value != null && value.matches("\\d{1,5}")) {
                final int port = Integer.parseInt(value);
                if (port > 0 && port <= 65535) {
                    return port;
                }
            }
        }
        final Path props = Path.of("server.properties");
        if (Files.isRegularFile(props)) {
            final Properties properties = new Properties();
            try (var in = Files.newInputStream(props)) {
                properties.load(in);
            }
            final String value = properties.getProperty("server-port");
            if (value != null && value.matches("\\d{1,5}")) {
                return Integer.parseInt(value);
            }
        }
        return 25565;
    }

    private static String fingerprint(final int port) {
        final String serverId = firstNonBlank(
            System.getenv("P_SERVER_UUID"),
            System.getenv("SERVER_UUID"),
            System.getenv("P_SERVER_ID"),
            "local"
        );
        final String material = serverId + "|" + port + "|" + Path.of("").toAbsolutePath().normalize();
        return sha256(material);
    }

    private static boolean validActivation(final String fingerprint) {
        if (!Files.isRegularFile(ACTIVATION)) {
            return false;
        }
        try {
            final Properties properties = new Properties();
            try (var in = Files.newInputStream(ACTIVATION)) {
                properties.load(in);
            }
            final String expected = sha256(fingerprint + "|" + EXPECTED_KEY_SHA256 + "|ZEROX-PAPER-1.21.11");
            return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                properties.getProperty("token", "").getBytes(StandardCharsets.US_ASCII)
            );
        } catch (Exception ignored) {
            return false;
        }
    }

    private static void runActivationServer(final int port, final String fingerprint) throws Exception {
        final CountDownLatch activated = new CountDownLatch(1);
        final HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        server.setExecutor(Executors.newFixedThreadPool(2, runnable -> {
            final Thread thread = new Thread(runnable, "ZEROX-License");
            thread.setDaemon(true);
            return thread;
        }));
        server.createContext("/", exchange -> page(
            exchange,
            200,
            "<h2>ZEROX Paper Activation</h2><p>Enter your license key to activate this server.</p>"
                + "<form method='post' action='/activate'><input name='key' type='password' required autofocus>"
                + "<button>Activate</button></form>"
        ));
        server.createContext("/activate", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                page(exchange, 405, "Method not allowed");
                return;
            }
            final String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            String key = "";
            for (String pair : body.split("&")) {
                final String[] keyValue = pair.split("=", 2);
                if (keyValue.length == 2 && keyValue[0].equals("key")) {
                    key = URLDecoder.decode(keyValue[1], StandardCharsets.UTF_8);
                }
            }
            if (!MessageDigest.isEqual(
                sha256(key.trim()).getBytes(StandardCharsets.US_ASCII),
                EXPECTED_KEY_SHA256.getBytes(StandardCharsets.US_ASCII)
            )) {
                page(exchange, 403, "<h3>Invalid license key</h3><a href='/'>Try again</a>");
                return;
            }
            final Properties properties = new Properties();
            properties.setProperty("format", "1");
            properties.setProperty("fingerprint", fingerprint);
            properties.setProperty("token", sha256(fingerprint + "|" + EXPECTED_KEY_SHA256 + "|ZEROX-PAPER-1.21.11"));
            properties.setProperty("activatedAt", Instant.now().toString());
            try (var out = Files.newOutputStream(ACTIVATION)) {
                properties.store(out, "ZEROX activation; no plaintext license is stored");
            }
            page(exchange, 200, "<h2>Activated</h2><p>The activation server will close and Minecraft will start.</p>");
            activated.countDown();
        });
        server.start();
        System.out.println("[ZEROX] First-run activation required.");
        System.out.println("[ZEROX] Open http://YOUR-SERVER-IP:" + port + "/ and enter the license key.");
        activated.await();
        server.stop(0);
        Thread.sleep(250L);
    }

    private static void page(final HttpExchange exchange, final int status, final String body) throws IOException {
        final String html = "<!doctype html><html><head><meta name='viewport' content='width=device-width'>"
            + "<title>ZEROX Activation</title><style>body{font-family:sans-serif;max-width:560px;margin:10vh auto;"
            + "padding:24px;background:#0b1020;color:#fff}input,button{padding:12px;margin:6px;font-size:16px}"
            + "</style></head><body>" + body + "</body></html>";
        final byte[] bytes = html.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void writeBuildMetadata() throws IOException {
        Files.writeString(
            DIR.resolve("build.properties"),
            "name=" + ZeroxBuildInfo.NAME + "\n"
                + "version=" + ZeroxBuildInfo.VERSION + "\n"
                + "mcVersion=" + ZeroxBuildInfo.MINECRAFT_VERSION + "\n"
                + "upstreamCommit=" + ZeroxBuildInfo.UPSTREAM_COMMIT + "\n"
                + "zeroxCommit=" + ZeroxBuildInfo.ZEROX_COMMIT + "\n"
                + "buildNumber=" + ZeroxBuildInfo.BUILD_NUMBER + "\n"
                + "buildTime=" + ZeroxBuildInfo.BUILD_TIME + "\n"
                + "profileVersion=2\n",
            StandardCharsets.UTF_8
        );
    }

    private static void setDefaultSystemProperty(final String key, final String value) {
        if (System.getProperty(key) == null) {
            System.setProperty(key, value);
        }
    }

    private static int parseInt(final String value, final int fallback) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static int clamp(final int value, final int minimum, final int maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private static String sha256(final String input) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(input.getBytes(StandardCharsets.UTF_8))
            ).toLowerCase(Locale.ROOT);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }

    private static String firstNonBlank(final String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "local";
    }
}
''', encoding="utf-8")

resource_dir = root / "paper-server/src/main/resources/META-INF"
resource_dir.mkdir(parents=True, exist_ok=True)
resource = {
    "name": "ZEROX Paper",
    "version": ZEROX_VERSION,
    "minecraftVersion": MC_VERSION,
    "upstreamPaperBuild": 132,
    "upstreamCommit": UPSTREAM_COMMIT,
    "zeroxCommit": zerox_commit,
    "buildNumber": build_number,
    "buildTime": build_time,
    "patchCount": 4,
    "sourceRepository": "https://github.com/manuekamjotsidhu-byte/Hello",
    "javaTarget": 21,
    "reproducible": False,
    "reproducibilityNote": "Build inputs are pinned; byte-for-byte reproducibility is not yet independently verified.",
}
(resource_dir / "zerox-build.json").write_text(json.dumps(resource, indent=2) + "\n", encoding="utf-8")

print("ZEROX v2 source patches applied to", root)

#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
main_candidates = list(root.glob('paper-server/src/minecraft/java/net/minecraft/server/Main.java')) + list(root.glob('paper-server/src/minecraft/net/minecraft/server/Main.java'))
if not main_candidates:
    raise SystemExit('Patched Main.java not found after applyPatches')
main = main_candidates[0]
text = main.read_text()
needle = 'SharedConstants.tryDetectVersion();'
insert = needle + '\n        io.papermc.paper.zerox.ZeroxBootstrap.activateAndPrepare(); // ZEROX'
if 'ZeroxBootstrap.activateAndPrepare' not in text:
    if needle not in text:
        raise SystemExit('Main bootstrap insertion point not found')
    main.write_text(text.replace(needle, insert, 1))

world = root / 'paper-server/src/main/java/io/papermc/paper/configuration/WorldConfiguration.java'
w = world.read_text()
replacements = {
    'public boolean doCollisionEntityLookups = true;': 'public boolean doCollisionEntityLookups = false; // ZEROX: avoid unnecessary armor-stand collision scans',
    'public boolean optimizeExplosions = false;': 'public boolean optimizeExplosions = true; // ZEROX: optimized explosion density calculation',
    'public boolean updatePathfindingOnBlockUpdate = true;': 'public boolean updatePathfindingOnBlockUpdate = false; // ZEROX: avoid global path recalculation storms',
}
for old, new in replacements.items():
    if old in w:
        w = w.replace(old, new, 1)
world.write_text(w)

pkg = root / 'paper-server/src/main/java/io/papermc/paper/zerox'
pkg.mkdir(parents=True, exist_ok=True)
(pkg / 'ZeroxBootstrap.java').write_text(r'''package io.papermc.paper.zerox;

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
    private ZeroxBootstrap() {}

    public static void activateAndPrepare() {
        try {
            Files.createDirectories(DIR);
            int port = detectPort();
            String fingerprint = fingerprint(port);
            if (!validActivation(fingerprint)) runActivationServer(port, fingerprint);
            writeBuildMetadata();
            System.out.println("[ZEROX] License verified. Starting ZEROX Paper 1.21.11.");
        } catch (Exception ex) {
            throw new IllegalStateException("ZEROX activation failed", ex);
        }
    }

    private static int detectPort() throws IOException {
        for (String name : new String[]{"SERVER_PORT", "PORT", "P_SERVER_PORT"}) {
            String value = System.getenv(name);
            if (value != null && value.matches("\\d{1,5}")) {
                int p = Integer.parseInt(value);
                if (p > 0 && p <= 65535) return p;
            }
        }
        Path props = Path.of("server.properties");
        if (Files.isRegularFile(props)) {
            Properties p = new Properties();
            try (var in = Files.newInputStream(props)) { p.load(in); }
            String v = p.getProperty("server-port");
            if (v != null && v.matches("\\d{1,5}")) return Integer.parseInt(v);
        }
        return 25565;
    }

    private static String fingerprint(int port) {
        String serverId = firstNonBlank(System.getenv("P_SERVER_UUID"), System.getenv("SERVER_UUID"), System.getenv("P_SERVER_ID"), "local");
        String material = serverId + "|" + port + "|" + Path.of("").toAbsolutePath().normalize();
        return sha256(material);
    }

    private static boolean validActivation(String fingerprint) {
        if (!Files.isRegularFile(ACTIVATION)) return false;
        try {
            Properties p = new Properties();
            try (var in = Files.newInputStream(ACTIVATION)) { p.load(in); }
            String expected = sha256(fingerprint + "|" + EXPECTED_KEY_SHA256 + "|ZEROX-PAPER-1.21.11");
            return MessageDigest.isEqual(expected.getBytes(StandardCharsets.US_ASCII), p.getProperty("token", "").getBytes(StandardCharsets.US_ASCII));
        } catch (Exception ignored) { return false; }
    }

    private static void runActivationServer(int port, String fingerprint) throws Exception {
        CountDownLatch activated = new CountDownLatch(1);
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        server.setExecutor(Executors.newFixedThreadPool(2, r -> { Thread t = new Thread(r, "ZEROX-License"); t.setDaemon(true); return t; }));
        server.createContext("/", ex -> page(ex, 200, "<h2>ZEROX Paper Activation</h2><p>Enter your license key to activate this server.</p><form method='post' action='/activate'><input name='key' type='password' required autofocus><button>Activate</button></form>"));
        server.createContext("/activate", ex -> {
            if (!"POST".equalsIgnoreCase(ex.getRequestMethod())) { page(ex, 405, "Method not allowed"); return; }
            String body = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            String key = "";
            for (String pair : body.split("&")) {
                String[] kv = pair.split("=", 2);
                if (kv.length == 2 && kv[0].equals("key")) key = URLDecoder.decode(kv[1], StandardCharsets.UTF_8);
            }
            if (!MessageDigest.isEqual(sha256(key.trim()).getBytes(StandardCharsets.US_ASCII), EXPECTED_KEY_SHA256.getBytes(StandardCharsets.US_ASCII))) {
                page(ex, 403, "<h3>Invalid license key</h3><a href='/'>Try again</a>"); return;
            }
            Properties p = new Properties();
            p.setProperty("format", "1");
            p.setProperty("fingerprint", fingerprint);
            p.setProperty("token", sha256(fingerprint + "|" + EXPECTED_KEY_SHA256 + "|ZEROX-PAPER-1.21.11"));
            p.setProperty("activatedAt", Instant.now().toString());
            try (var out = Files.newOutputStream(ACTIVATION)) { p.store(out, "ZEROX activation; no plaintext license is stored"); }
            page(ex, 200, "<h2>Activated</h2><p>The activation server will close and Minecraft will start on this port.</p>");
            activated.countDown();
        });
        server.start();
        System.out.println("[ZEROX] First-run activation required.");
        System.out.println("[ZEROX] Open http://YOUR-SERVER-IP:" + port + "/ and enter the license key.");
        activated.await();
        server.stop(0);
        Thread.sleep(500L);
    }

    private static void page(HttpExchange ex, int status, String body) throws IOException {
        String html = "<!doctype html><html><head><meta name='viewport' content='width=device-width'><title>ZEROX Activation</title><style>body{font-family:sans-serif;max-width:560px;margin:10vh auto;padding:24px;background:#0b1020;color:#fff}input,button{padding:12px;margin:6px;font-size:16px}</style></head><body>" + body + "</body></html>";
        byte[] bytes = html.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
        ex.getResponseHeaders().set("Cache-Control", "no-store");
        ex.sendResponseHeaders(status, bytes.length);
        try (var out = ex.getResponseBody()) { out.write(bytes); }
    }

    private static void writeBuildMetadata() throws IOException {
        Files.writeString(DIR.resolve("build.properties"), "name=ZEROX Paper\nmcVersion=1.21.11\nupstream=6da8af7ca4e29f4ea6961905a96d9f244980c932\nprofileVersion=1\n", StandardCharsets.UTF_8);
    }

    private static String sha256(String s) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8))).toLowerCase(Locale.ROOT);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }

    private static String firstNonBlank(String... values) {
        for (String v : values) if (v != null && !v.isBlank()) return v;
        return "local";
    }
}
''')

print('ZEROX source patches applied to', root)

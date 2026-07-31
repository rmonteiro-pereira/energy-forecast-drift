import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
// `vitest/config` re-exports vite's defineConfig with the `test` block typed, so
// the banner tests below are configured in the same file as the build.
import { defineConfig } from "vitest/config";

const here = dirname(fileURLToPath(import.meta.url));

/** The published surface of the Python side. The dashboard reads nothing else. */
const METRICS_DIR = resolve(here, "..", "metrics");
const DATA_ROUTE = "/data/";

/**
 * Serve `metrics/*.json` at `/data/*` in dev, and copy them into `dist/data/`
 * on build.
 *
 * The alternative — importing the JSON directly — would inline it into the
 * bundle, so a metrics refresh would need a rebuild and the dashboard could not
 * be pointed at a fresher copy. Keeping them as fetched files means the build
 * output is a static site that reads whatever `data/` the host serves.
 */
function metricsPlugin(): Plugin {
  return {
    name: "energy-forecast-drift:metrics",

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith(DATA_ROUTE)) return next();

        const name = req.url.slice(DATA_ROUTE.length).split("?")[0];
        // Path traversal guard: only bare filenames out of metrics/ are servable.
        if (!/^[\w.-]+\.(json|png)$/.test(name)) return next();

        const file = resolve(METRICS_DIR, name);
        if (!existsSync(file)) {
          res.statusCode = 404;
          return res.end(`no such metrics file: ${name}`);
        }
        res.setHeader(
          "Content-Type",
          name.endsWith(".png") ? "image/png" : "application/json",
        );
        // Never cache: the daily pipeline rewrites these under a running dev server.
        res.setHeader("Cache-Control", "no-store");
        return res.end(readFileSync(file));
      });
    },

    closeBundle() {
      const out = resolve(here, "dist", "data");
      mkdirSync(out, { recursive: true });

      if (!existsSync(METRICS_DIR)) {
        this.warn(`no metrics/ directory at ${METRICS_DIR} — dist/data will be empty`);
        return;
      }
      for (const name of readdirSync(METRICS_DIR)) {
        if (name.endsWith(".json")) copyFileSync(resolve(METRICS_DIR, name), resolve(out, name));
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), metricsPlugin()],
  // Relative so `dist/` works from a subdirectory as well as a domain root.
  base: "./",
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

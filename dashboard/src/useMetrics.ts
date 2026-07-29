/**
 * Load the four artifacts the Python side publishes.
 *
 * They are *fetched*, not imported: importing would inline them into the bundle,
 * so a metrics refresh would need a rebuild and the built site could never be
 * pointed at a fresher `data/`. Vite's `metricsPlugin` serves `metrics/` at
 * `/data/` in dev and copies it into `dist/data/` on build.
 */

import { useCallback, useEffect, useState } from "react";

import type { DriftArtifact, ForecastArtifact, Metrics, MonitorArtifact, PipelineArtifact } from "./types";

const BASE = `${import.meta.env.BASE_URL}data`.replace(/\/{2,}/g, "/");

export interface LoadState {
  metrics: Metrics | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

async function fetchJson<T>(name: string): Promise<T> {
  const response = await fetch(`${BASE}/${name}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${name}: HTTP ${response.status}. Run \`uv run python -m pipeline.daily\` first.`);
  }
  return (await response.json()) as T;
}

export function useMetrics(): LoadState {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      fetchJson<ForecastArtifact>("forecast.json"),
      fetchJson<MonitorArtifact>("monitor.json"),
      fetchJson<DriftArtifact>("drift.json"),
      fetchJson<PipelineArtifact>("pipeline.json"),
    ])
      .then(([forecast, monitor, drift, pipeline]) => {
        if (cancelled) return;
        setMetrics({ forecast, monitor, drift, pipeline });
        setError(null);
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { metrics, error, loading, reload };
}

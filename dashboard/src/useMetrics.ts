/**
 * Load the five artifacts the Python side publishes.
 *
 * They are *fetched*, not imported: importing would inline them into the bundle,
 * so a metrics refresh would need a rebuild and the built site could never be
 * pointed at a fresher `data/`. Vite's `metricsPlugin` serves `metrics/` at
 * `/data/` in dev and copies it into `dist/data/` on build.
 */

import { useCallback, useEffect, useState } from "react";

import type {
  DriftArtifact,
  ForecastArtifact,
  Metrics,
  ModelArtifact,
  MonitorArtifact,
  PipelineArtifact,
} from "./types";

const BASE = `${import.meta.env.BASE_URL}data`.replace(/\/{2,}/g, "/");

export interface LoadState {
  metrics: Metrics | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * `model.json` is written by a different command from the other four, so the
 * failure message has to name the right one — "run the daily pipeline" is
 * advice that cannot produce it, and would send someone in a circle.
 */
const PRODUCER: Record<string, string> = {
  "model.json": "uv run python -m models.train",
};

async function fetchJson<T>(name: string): Promise<T> {
  const response = await fetch(`${BASE}/${name}`, { cache: "no-store" });
  if (!response.ok) {
    const command = PRODUCER[name] ?? "uv run python -m pipeline.daily";
    throw new Error(`${name}: HTTP ${response.status}. Run \`${command}\` first.`);
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
      // Written by `models.train`, not by the daily run, so it changes only when
      // a model is retrained. It carries the backtest — the answer to "is this
      // any good?", which the four daily artifacts do not contain.
      fetchJson<ModelArtifact>("model.json"),
    ])
      .then(([forecast, monitor, drift, pipeline, model]) => {
        if (cancelled) return;
        setMetrics({ forecast, monitor, drift, pipeline, model });
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

/**
 * The shapes of `metrics/*.json`.
 *
 * These mirror what `pipeline/daily.py` writes. They are deliberately partial —
 * only the fields the dashboard actually reads are typed, so adding a key on the
 * Python side never breaks the build, while renaming one the dashboard uses
 * does, which is the direction that matters.
 */

export type Severity = "ok" | "warn" | "alert";
export type VerdictAction = "retrain" | "watch" | "none";

/** Present on every artifact. `is_real === false` drives the banner. */
export interface Provenance {
  generated_at_utc: string;
  is_real: boolean;
  warning: string | null;
}

export interface ModelInfo {
  source?: string;
  uri?: string | null;
  version?: string | null;
  alias?: string | null;
  reason?: string;
  trained_on_real_data?: boolean;
  data_kind?: string | null;
  train_data_end_utc?: string | null;
}

export interface ForecastPoint {
  target_utc: string;
  horizon_h?: number;
  forecast_mwh: number;
  actual_mwh?: number;
  error_mwh?: number;
}

export interface ForecastArtifact extends Provenance {
  units: string;
  horizon_shown_h: number;
  note: string;
  served_model: ModelInfo;
  monitoring_model: ModelInfo;
  data: { kind: string; is_real: boolean };
  history: ForecastPoint[];
  forward: ForecastPoint[];
}

export interface ErrorSummary {
  n: number;
  mae: number | null;
  mape_pct: number | null;
  rmse: number | null;
  bias: number | null;
}

export interface MonitorDay {
  day_utc: string;
  window: "reference" | "current";
  mae: number;
  mape_pct: number;
  bias: number;
  mae_rolling: number;
  mape_rolling: number;
  n: number;
}

export interface MonitorArtifact extends Provenance {
  rolling_window_hours: number;
  reference: ErrorSummary;
  current: ErrorSummary;
  mae_degradation: number;
  mape_degradation_pp: number | null;
  alert_line_mae: number | null;
  severity: Severity;
  summary: string;
  daily: MonitorDay[];
  monitoring_model: ModelInfo;
  served_model: ModelInfo;
}

export interface DriftColumn {
  column: string;
  severity: Severity;
  drift_detected: boolean;
  insufficient_data: boolean;
  deterministic: boolean;
  psi: { psi: number; bins: number; binning: string };
  ks: { statistic: number; p_value: number; significant: boolean };
  distribution: { mean_shift: number | null };
}

export interface DriftSection {
  drift_type: string;
  severity: Severity;
  drift_detected: boolean;
  summary: string;
  description?: string;
  columns?: DriftColumn[];
  columns_excluded_deterministic?: string[];
  mae_degradation?: number;
}

export interface TimelinePoint {
  day_utc: string;
  window: "reference" | "current";
  n: number;
  target_psi: number;
  prediction_psi: number;
  feature_max_psi: number | null;
  feature_max_column: string | null;
  mae: number;
}

export interface Verdict {
  should_retrain: boolean;
  action: VerdictAction;
  severity: Severity;
  rule: string;
  rationale: string;
  signals: Record<string, Severity>;
  reasons: {
    drift_type: string;
    severity: Severity;
    metric: string;
    value: number | null;
    threshold: number | null;
    detail: string;
  }[];
  evaluated_at_utc: string;
}

export interface DriftArtifact extends Provenance {
  verdict: Verdict;
  thresholds: { psi_warn: number; psi_alert: number; mae_degradation_alert: number };
  windows: {
    reference_start_utc: string;
    current_start_utc: string;
    panel_end_utc: string;
    rows: { train: number; reference: number; current: number };
  };
  data: { kind: string; is_real: boolean };
  drift: Record<string, DriftSection>;
  timeline?: { description: string; trailing_window_days: number; points: TimelinePoint[] };
  evidently?: { status: string; drifted_columns?: number | null };
  served_model?: ModelInfo;
  monitoring_model?: ModelInfo;
}

export interface PipelineStep {
  step: string;
  status: string;
  seconds: number;
}

export interface PipelineArtifact extends Provenance {
  status: string;
  error: string | null;
  entrypoint: string;
  seconds: number;
  steps: PipelineStep[];
  artifacts: string[];
  served_model: ModelInfo | null;
  monitoring_model: ModelInfo | null;
}

export interface Metrics {
  forecast: ForecastArtifact;
  monitor: MonitorArtifact;
  drift: DriftArtifact;
  pipeline: PipelineArtifact;
}

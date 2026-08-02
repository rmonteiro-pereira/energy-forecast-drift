/**
 * The page. Order is deliberate:
 *
 *   1. the provenance banner  — what these numbers are, before any of them
 *   2. the verdict + signals  — the one decision the whole repo exists to make
 *   3. the headline stats     — MAE now vs the reference, the retrain line
 *   4. the charts             — forecast, drift over time, MAE trend, PSI now
 *
 * A reader who stops after the first screen should still leave with the two
 * facts that matter: whether the data is real, and whether the model needs
 * retraining.
 */

import { useState } from "react";

import { DriftTimelineChart } from "./charts/DriftTimelineChart";
import { FeaturePsiChart } from "./charts/FeaturePsiChart";
import { ForecastChart } from "./charts/ForecastChart";
import { MaeTrendChart } from "./charts/MaeTrendChart";
import { Card, ProvenanceBanner, Stat, StatusDot } from "./components";
import { compact, precise, shortDateTime } from "./chartBase";
import { useThemeTokens, type ThemeChoice } from "./theme";
import type { Metrics, Severity, VerdictAction } from "./types";
import { useMetrics } from "./useMetrics";

const ACTION_COPY: Record<VerdictAction, { title: string; blurb: string }> = {
  retrain: {
    title: "Retrain",
    blurb: "A retrain rule fired. The champion should be refit before it is trusted further.",
  },
  watch: {
    title: "Watch",
    blurb:
      "Drift is visible but no retrain rule is satisfied — a leading indicator without measured harm.",
  },
  none: { title: "Healthy", blurb: "All four drift signals are inside their thresholds." },
};

export function App() {
  const [theme, setTheme] = useState<ThemeChoice>("system");
  const tokens = useThemeTokens(theme);
  const { metrics, error, loading, reload } = useMetrics();

  if (error) {
    return (
      <div className="page">
        <div className="state">
          <p>
            <strong>Could not load the metrics.</strong>
          </p>
          <p>{error}</p>
          <button type="button" onClick={reload}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="page">
        <div className="state">Loading metrics…</div>
      </div>
    );
  }

  return (
    <div className="page">
      {/* Refetch holds the previous render at reduced opacity — no skeleton flash. */}
      <div className={loading ? "stale" : undefined}>
        <Dashboard metrics={metrics} tokens={tokens} theme={theme} onTheme={setTheme} />
      </div>
    </div>
  );
}

function Dashboard({
  metrics,
  tokens,
  theme,
  onTheme,
}: {
  metrics: Metrics;
  tokens: ReturnType<typeof useThemeTokens>;
  theme: ThemeChoice;
  onTheme: (choice: ThemeChoice) => void;
}) {
  const { forecast, monitor, drift, pipeline } = metrics;
  const verdict = drift.verdict;
  const action = ACTION_COPY[verdict.action];
  const served = pipeline.served_model ?? forecast.served_model;

  return (
    <>
      <header className="masthead">
        <div>
          <h1>energy-forecast-drift</h1>
          <p>
            Hourly electricity demand forecasting for PJM, with the drift loop around it. This
            page reads <code>metrics/*.json</code> — the same files the daily pipeline commits.
          </p>
        </div>
        <div className="masthead-actions">
          <span className="tag">
            refreshed {shortDateTime(pipeline.generated_at_utc)} UTC
          </span>
          <button
            type="button"
            onClick={() => onTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle colour theme"
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </header>

      <ProvenanceBanner
        isReal={drift.is_real}
        warning={drift.warning}
        dataKind={drift.data.kind}
        generatedAt={drift.generated_at_utc}
      />

      <Card
        title="Retrain verdict"
        aside={<span className="tag">rule {verdict.rule}</span>}
        note={verdict.rationale}
      >
        <div className="verdict">
          <div className="verdict-headline">
            <span
              className={`dot status-${verdict.action === "retrain" ? "alert" : verdict.action === "watch" ? "warn" : "ok"}`}
              style={{ width: 14, height: 14 }}
              aria-hidden="true"
            />
            <div>
              <div className="verdict-figure">{action.title}</div>
              <div className="verdict-rule">
                should_retrain = {String(verdict.should_retrain)}
              </div>
            </div>
          </div>
          <p className="card-note" style={{ margin: 0, maxWidth: "48ch" }}>
            {action.blurb}
          </p>
        </div>

        <div className="signals">
          {Object.entries(verdict.signals).map(([name, severity]) => (
            <Signal
              key={name}
              name={name}
              severity={severity as Severity}
              detail={drift.drift[name]?.summary ?? ""}
            />
          ))}
        </div>
      </Card>

      <div className="stats">
        <Stat
          label="MAE — current window"
          value={monitor.current.mae == null ? "—" : compact.format(monitor.current.mae)}
          unit="MWh"
          sub={`reference ${monitor.reference.mae == null ? "—" : compact.format(monitor.reference.mae)} MWh`}
        />
        <Stat
          label="Degradation"
          value={`${(monitor.mae_degradation * 100).toFixed(1)}%`}
          sub={`retrain at +${(drift.thresholds.mae_degradation_alert * 100).toFixed(0)}%`}
        />
        <Stat
          label="MAPE — current window"
          value={monitor.current.mape_pct == null ? "—" : precise.format(monitor.current.mape_pct)}
          unit="%"
          sub={
            monitor.mape_degradation_pp == null
              ? undefined
              : `${monitor.mape_degradation_pp >= 0 ? "+" : ""}${precise.format(monitor.mape_degradation_pp)} pp vs reference`
          }
        />
        <Stat
          label="Served model"
          value={served?.version ? `v${served.version}` : "—"}
          sub={served?.source === "mlflow_registry" ? "registry @champion" : (served?.source ?? "none")}
        />
      </div>

      <Card
        title="Forecast vs actual"
        note={forecast.note}
        aside={<span className="tag">horizon ≤ {forecast.horizon_shown_h}h</span>}
      >
        <ForecastChart forecast={forecast} tokens={tokens} />
      </Card>

      <Card
        title="Drift over time"
        note={
          drift.timeline?.description ??
          "PSI of a trailing window against the reference, one point per day."
        }
        aside={
          <span className="tag">
            log scale — feature PSI runs orders of magnitude above the rest
          </span>
        }
      >
        <DriftTimelineChart drift={drift} tokens={tokens} />
      </Card>

      <Card
        title="Rolling forecast error"
        note={`${monitor.summary}. The shaded band is the current window; the model that produced these errors never trained on either window.`}
        aside={
          <span className="tag">
            <StatusDot severity={monitor.severity} />
          </span>
        }
      >
        <MaeTrendChart monitor={monitor} tokens={tokens} />
      </Card>

      <Card
        title="Feature drift right now"
        note={
          <>
            {drift.drift.feature?.summary}. Greyed dots are deterministic calendar columns —
            reported, but excluded from the verdict, because their PSI measures which dates the
            windows cover rather than the data. Dots rather than bars on purpose: PSI here spans
            three orders of magnitude, and a bar length measured from a log axis&rsquo; minimum
            would make a feature at 0.02 look two thirds as drifted as one at 6.7.
          </>
        }
      >
        <FeaturePsiChart drift={drift} tokens={tokens} />
      </Card>

      <footer className="footer">
        <p>
          Pipeline <code>{pipeline.entrypoint}</code> — {pipeline.status} in{" "}
          {pipeline.seconds.toFixed(1)}s ({pipeline.steps.map((s) => s.step).join(" → ")}).
        </p>
        <p>
          Reference window {shortDateTime(drift.windows.reference_start_utc)} →{" "}
          {shortDateTime(drift.windows.current_start_utc)} ·{" "}
          {compact.format(drift.windows.rows.reference)} rows. Current window{" "}
          {shortDateTime(drift.windows.current_start_utc)} →{" "}
          {shortDateTime(drift.windows.panel_end_utc)} ·{" "}
          {compact.format(drift.windows.rows.current)} rows.
        </p>
        {/*
          Not boilerplate, and not optional. Open-Meteo publishes under CC BY 4.0
          and asks for the credit next to where the data is shown — this page is
          that place, and the charts above are adapted material, not the series
          itself. The README carrying it is not enough: §3(a)(1) attaches the
          condition to each point of sharing.
        */}
        <p>
          Weather data by <a href="https://open-meteo.com/">Open-Meteo.com</a>, licensed{" "}
          <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> and modified —
          aggregated to hourly features and scored, not shown raw. Demand data from the{" "}
          <a href="https://www.eia.gov/opendata/">U.S. Energy Information Administration</a>.
        </p>
      </footer>
    </>
  );
}

function Signal({
  name,
  severity,
  detail,
}: {
  name: string;
  severity: Severity;
  detail: string;
}) {
  return (
    <div className="signal">
      <div className="signal-head">
        <StatusDot severity={severity} />
        <span>{name}</span>
      </div>
      <p className="signal-detail">{detail}</p>
    </div>
  );
}

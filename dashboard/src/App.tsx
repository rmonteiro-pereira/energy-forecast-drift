/**
 * The page.
 *
 * It used to open on the retrain verdict, which is the last question a first-time
 * reader has and the first one this repository's author has. Someone who lands
 * here cold does not know what is being forecast, whether it works, or how it was
 * built — and a page that answers "should the model be retrained?" before any of
 * those is answering into a vacuum.
 *
 * So the order follows what a reader needs in the order they need it:
 *
 *   1. what this is       — the problem, in two sentences, before any number
 *   2. is the data real   — the honesty banner; every number below inherits it
 *   3. what it delivers   — the backtest headline: accuracy, and against what
 *   4. how it was made    — the six stages, each with the decision behind it
 *   5. the forecast       — the actual output, plotted against what happened
 *   6. drift monitoring   — the part that makes it a system rather than a model
 *
 * A reader who stops after the first screen leaves knowing what was built, how
 * accurate it is, and against which baseline. A reader who stops after the
 * second knows how, and why each choice was made.
 */

import { useState } from "react";

import { DriftTimelineChart } from "./charts/DriftTimelineChart";
import { FeaturePsiChart } from "./charts/FeaturePsiChart";
import { ForecastChart } from "./charts/ForecastChart";
import { MaeTrendChart } from "./charts/MaeTrendChart";
import { Card, ProvenanceBanner, Stat, StatusDot, VerdictCard } from "./components";
import { compact, precise, shortDateTime } from "./chartBase";
import { useThemeTokens, type ThemeChoice } from "./theme";
import type { Metrics, ModelArtifact } from "./types";
import { useMetrics } from "./useMetrics";

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
  const { forecast, drift, pipeline, model } = metrics;
  const served = pipeline.served_model ?? forecast.served_model;

  return (
    <>
      <header className="masthead">
        <div>
          <h1>energy-forecast-drift</h1>
          <p className="masthead-lede">
            Day-ahead hourly electricity demand forecasting for{" "}
            <strong>{model.data.respondent ?? "PJM"}</strong>, with the drift-monitoring loop
            that decides when the model has stopped being trustworthy.
          </p>
        </div>
        <div className="masthead-actions">
          <span className="tag">refreshed {shortDateTime(pipeline.generated_at_utc)} UTC</span>
          <button
            type="button"
            onClick={() => onTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle colour theme"
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </header>

      <WhatThisIs model={model} />

      <ProvenanceBanner
        isReal={drift.is_real}
        warning={drift.warning}
        dataKind={drift.data.kind}
        generatedAt={drift.generated_at_utc}
      />

      <Results model={model} />

      <HowItWasMade model={model} served={served?.version ?? null} />

      <Card
        title="The forecast, against what actually happened"
        note={forecast.note}
        aside={<span className="tag">horizon ≤ {forecast.horizon_shown_h}h</span>}
      >
        <ForecastChart forecast={forecast} tokens={tokens} />
      </Card>

      <DriftMonitoring metrics={metrics} tokens={tokens} />

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

/**
 * The problem, before any number. Two sentences on what is being predicted and
 * why the error has a price, then what the repository actually contains.
 */
function WhatThisIs({ model }: { model: ModelArtifact }) {
  const sites = model.data.weather_sites?.length ?? 0;
  const panelRows = model.data.panel?.rows;

  return (
    <section className="explainer">
      <div className="explainer-block">
        <h2>What this is</h2>
        <p>
          Grid operators must commit generation a day before it is consumed. Every hour of that
          commitment rests on a forecast of how much electricity the region will draw, and being
          wrong is expensive in both directions — too little and reserves get bought at the spot
          price, too much and plants are paid to idle.
        </p>
        <p>
          This forecasts the next <strong>24 hours</strong> of demand for{" "}
          {model.data.respondent ?? "PJM"}, the largest grid operator in the United States, one
          value per hour. It is a complete system rather than a notebook: ingestion, features,
          a walk-forward benchmark against a real baseline, a model registry, a daily cron, and
          the drift monitoring that decides when the model needs to be refit.
        </p>
      </div>
      <div className="explainer-block">
        <h2>What it runs on</h2>
        <ul className="fact-list">
          <li>
            <strong>{panelRows ? compact.format(panelRows) : "—"} hours</strong> of real demand
            from the U.S. Energy Information Administration
          </li>
          <li>
            <strong>{sites || "—"} weather sites</strong> across the region, including{" "}
            <em>archived forecasts</em> — what the weather service predicted, not what the
            weather turned out to be
          </li>
          <li>
            <strong>{model.models.challenger.n_features} features</strong>: calendar, holidays,
            demand lags and rolling statistics, observed and forecast weather
          </li>
          <li>
            Refreshed every morning at 06:20 UTC by a scheduled job that publishes its own
            numbers through a pull request
          </li>
        </ul>
      </div>
    </section>
  );
}

/**
 * The headline. A model is only as good as the thing it beat, so the baseline is
 * given equal weight rather than being a footnote — and the caveats are on the
 * same screen as the numbers, not a click away.
 */
function Results({ model }: { model: ModelArtifact }) {
  const lgbm = model.metrics.lightgbm.overall;
  const baseline = model.metrics.baseline.overall;
  const comparison = model.metrics.comparison;
  const ablation = model.ablation?.forecast_weather;
  const weatherHelped = ablation?.measured && ablation.helped && ablation.mae_delta_pct != null;

  return (
    <>
      <h2 className="section-heading">What it delivers</h2>
      <div className="stats">
        <Stat
          label="Forecast error (MAPE)"
          value={lgbm.mape_pct == null ? "—" : precise.format(lgbm.mape_pct)}
          unit="%"
          sub={`${lgbm.mae == null ? "—" : compact.format(lgbm.mae)} MWh average absolute error`}
        />
        <Stat
          label="Versus the baseline"
          value={`${comparison.mae_delta_pct.toFixed(0)}%`}
          sub={`error against last week's same hour (${baseline.mape_pct == null ? "—" : precise.format(baseline.mape_pct)}% MAPE)`}
        />
        <Stat
          label="Horizons won"
          value={`${comparison.horizons_won}/${comparison.horizons_total}`}
          sub="beats the baseline at every hour ahead, 1h to 24h"
        />
        <Stat
          label="Weather forecast features"
          value={weatherHelped ? `${ablation.mae_delta_pct!.toFixed(0)}%` : "—"}
          sub={
            weatherHelped
              ? "error when they are added — measured by removing them and refitting"
              : "not measured on this run"
          }
        />
      </div>
      <p className="section-note">
        Measured over <strong>{model.backtest.weeks} weeks</strong> and{" "}
        <strong>{model.backtest.folds} walk-forward refits</strong> (
        {shortDateTime(model.backtest.first_cutoff_utc)} →{" "}
        {shortDateTime(model.backtest.last_cutoff_utc)}), never on data the model had seen. For
        scale, published day-ahead errors for large ISOs sit around 2–3% MAPE — so this is in
        the right band, on a summer window that is the easier half of the year. It has not been
        tested through a winter peak, and eight weeks is a short evidence base; both are stated
        rather than smoothed over.
      </p>
    </>
  );
}

/**
 * How, as six decisions rather than six nouns. Each stage names the trap it
 * avoids, because "walk-forward backtest" means nothing to a reader who has not
 * already lost a week to a leaking one.
 */
function HowItWasMade({ model, served }: { model: ModelArtifact; served: string | null }) {
  const stages = [
    {
      step: "Ingest",
      title: "Demand and weather, incrementally",
      body: (
        <>
          Hourly demand from the EIA, hourly weather from Open-Meteo across{" "}
          {model.data.weather_sites?.length ?? 0} sites. Pulls are idempotent and resumable, so a
          failed morning does not lose a day or double-count one.
        </>
      ),
    },
    {
      step: "Features",
      title: "Weather forecasts, masked by publication time",
      body: (
        <>
          The model uses <em>forecast</em> weather, which is what would actually be available
          when a day-ahead forecast is made. The trap is using the forecast that was published
          after the moment being simulated. Each archived forecast therefore carries the hour it
          became public, and a feature is null until then — a mask that costs accuracy and buys
          the right to believe the number.
        </>
      ),
    },
    {
      step: "Model",
      title: "One LightGBM across all 24 horizons",
      body: (
        <>
          Horizon is a feature rather than a separate model per hour, so all{" "}
          {model.backtest.horizons_h.length} share the same fit and the same statistical
          strength. Direct, not recursive: a 24-hour forecast is predicted in one step instead of
          feeding predictions back in and compounding their errors.
        </>
      ),
    },
    {
      step: "Backtest",
      title: `${model.backtest.folds} refits, one per day, none looking forward`,
      body: (
        <>
          {model.backtest.protocol}. The model is refit at each daily cutoff on data available
          only up to that point, then scored on the next 24 hours. The baseline —{" "}
          {model.models.baseline.description} — runs on the identical folds and horizons, so the
          comparison is like for like.
        </>
      ),
    },
    {
      step: "Registry",
      title: "Promotion is conditional, not automatic",
      body: (
        <>
          Runs, parameters and metrics go to MLflow. A model becomes{" "}
          <code>@champion</code>
          {served ? ` (currently v${served})` : ""} only if it beats the baseline on the same
          backtest, and it is tagged with the last hour of its training data — the tag the drift
          monitor reads below.
        </>
      ),
    },
    {
      step: "Daily",
      title: "The loop runs itself",
      body: (
        <>
          A scheduled job re-ingests, re-scores, re-runs the drift detectors and opens a pull
          request with the refreshed numbers. The page you are reading is those files; nothing
          here is typed in by hand.
        </>
      ),
    },
  ];

  return (
    <>
      <h2 className="section-heading">How it was made</h2>
      <ol className="stages">
        {stages.map((stage, index) => (
          <li key={stage.step} className="stage">
            <div className="stage-mark">
              <span className="stage-index">{index + 1}</span>
              <span className="stage-step">{stage.step}</span>
            </div>
            <div className="stage-body">
              <h3>{stage.title}</h3>
              <p>{stage.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}

/**
 * The drift half, with the question stated before the answer.
 *
 * The verdict card has two shapes because the pipeline has two states, and
 * collapsing them is what once put "Retrain" on a model that had been trained
 * that morning. When the champion's training data reaches the end of the panel
 * there is nothing after it to measure, and the honest artifact says so instead
 * of computing a verdict from windows the model already learned.
 */
function DriftMonitoring({
  metrics,
  tokens,
}: {
  metrics: Metrics;
  tokens: ReturnType<typeof useThemeTokens>;
}) {
  const { monitor, drift } = metrics;
  const verdict = drift.verdict;

  return (
    <>
      <h2 className="section-heading">Is the model still trustworthy?</h2>
      <p className="section-note">
        A model is fitted on the world as it was. The world moves — a new heatwave pattern,
        a change in industrial load, a meter revision — and accuracy decays without anything
        failing loudly. This half of the project watches four signals for that, and turns them
        into one decision: refit, or leave it alone. Drift is measured from the moment training
        ended, not from the calendar, so a model retrained this morning starts at zero by
        construction rather than by luck.
      </p>

      <Card
        title="Retrain verdict"
        aside={<span className="tag">rule {verdict.rule}</span>}
        note={verdict.rationale}
      >
        <VerdictCard drift={drift} />
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
          label="Rolling error"
          value={monitor.severity === "ok" ? "Stable" : monitor.severity === "warn" ? "Warning" : "Alert"}
          sub={`measured by a model that trained on neither window`}
        />
      </div>

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
            {drift.drift.feature?.summary ?? "No feature drift was measured on this run."} Greyed
            dots are deterministic calendar columns — reported, but excluded from the verdict,
            because their PSI measures which dates the windows cover rather than the data. Dots
            rather than bars on purpose: PSI here spans three orders of magnitude, and a bar
            length measured from a log axis&rsquo; minimum would make a feature at 0.02 look two
            thirds as drifted as one at 6.7.
          </>
        }
      >
        <FeaturePsiChart drift={drift} tokens={tokens} />
      </Card>
    </>
  );
}


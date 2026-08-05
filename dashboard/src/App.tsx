/**
 * The page, v2 — a dashboard first and a writeup second.
 *
 * v1 was an article with two charts: the reader met three paragraphs before the
 * first number, and the drift verdict — the thesis of the project — lived at the
 * bottom of the scroll. v2 inverts the proportion. The first screen answers, in
 * order and without scrolling: is this real data (the pill and the banner), does
 * it beat the baseline and by how much (the KPI row), and what is today's drift
 * verdict (the panel beside them). Everything below is exploration.
 *
 * Every number on the page comes from `metrics/*.json`. Where the artifact says
 * a measurement does not exist yet — drift right after a retrain, an empty
 * timeline — the section renders the artifact's own reason instead of a
 * plausible placeholder. The honesty signals (`is_real`, `warning`,
 * `measurable`) drive the UI; nothing here overrides them.
 */

import { useState } from "react";

import { DriftTimelineChart } from "./charts/DriftTimelineChart";
import { FeaturePsiChart } from "./charts/FeaturePsiChart";
import { ForecastChart } from "./charts/ForecastChart";
import { HorizonChart } from "./charts/HorizonChart";
import { ImportanceChart } from "./charts/ImportanceChart";
import { MaeTrendChart } from "./charts/MaeTrendChart";
import {
  Card,
  EmptyPanel,
  Kpi,
  LiveBadge,
  LoopStrip,
  ProvenanceBanner,
  Stat,
  StatusDot,
  VerdictCard,
} from "./components";
import { compact, precise, shortDateTime } from "./chartBase";
import { useThemeTokens, type ThemeChoice } from "./theme";
import type { Metrics, ModelArtifact } from "./types";
import { useMetrics } from "./useMetrics";

const REPO_URL = "https://github.com/rmonteiro-pereira/energy-forecast-drift";

/**
 * `?theme=light|dark` pins the initial theme — for sharing a specific look and
 * for screenshotting both modes without a pointer. The toggle still wins after
 * load, and the default remains the OS preference.
 */
function initialTheme(): ThemeChoice {
  const requested = new URLSearchParams(window.location.search).get("theme");
  return requested === "light" || requested === "dark" ? requested : "system";
}

export function App() {
  const [theme, setTheme] = useState<ThemeChoice>(initialTheme);
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

/** A tiny load waveform, drawn inline so it inherits the current colour. */
function Wordmark() {
  return (
    <svg className="wordmark-pulse" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M1 14h4l2.5-8 4 12 3-8 1.5 4H23"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
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
  const { forecast, monitor, drift, pipeline, model } = metrics;
  const served = pipeline.served_model ?? forecast.served_model;
  const trainEnd = served?.train_data_end_utc ?? drift.served_model?.train_data_end_utc ?? null;

  return (
    <>
      <nav className="topbar" aria-label="Page">
        <a className="wordmark" href="#top">
          <Wordmark />
          energy-forecast-drift
        </a>
        <div className="topnav">
          <a href="#forecast">Forecast</a>
          <a href="#drift">Drift</a>
          <a href="#model">Model vs baseline</a>
          <a href="#loop">The loop</a>
        </div>
        <div className="topbar-actions">
          <LiveBadge isReal={drift.is_real} />
          <span className="tag tag-mono refreshed-tag">
            refreshed {shortDateTime(pipeline.generated_at_utc)} UTC
          </span>
          {/* The visible word is part of the accessible name (WCAG 2.5.3). */}
          <button type="button" onClick={() => onTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? "Light" : "Dark"}
            <span className="sr-only"> theme</span>
          </button>
        </div>
      </nav>

      <ProvenanceBanner
        isReal={drift.is_real}
        warning={drift.warning}
        dataKind={drift.data.kind}
        generatedAt={drift.generated_at_utc}
      />

      <main>
      <header className="hero" id="top">
        <div className="hero-title">
          <h1>energy-forecast-drift</h1>
          <p className="hero-thesis">
            Hourly demand forecasting for {model.data.respondent ?? "PJM"}, the largest grid
            operator in the US — <em>the point is not the forecast, it&rsquo;s the loop around
            it</em>: the drift monitor that decides, in public and every day, whether the model
            is still trustworthy.
          </p>
          <div className="hero-meta">
            {model.data.panel ? (
              <span className="tag tag-mono">
                {/* "real" is earned from the flag, never asserted by copy. */}
                {compact.format(model.data.panel.rows)} h of{" "}
                {model.is_real ? "real demand" : "fixture demand"}
              </span>
            ) : null}
            {model.data.weather_sites?.length ? (
              <span className="tag tag-mono">{model.data.weather_sites.length} weather sites</span>
            ) : null}
            <span className="tag tag-mono">{forecast.horizon_shown_h} h ahead, hourly</span>
            {served?.version ? (
              <span className="tag tag-mono">champion v{served.version}</span>
            ) : null}
          </div>
        </div>

        <KpiRow model={model} />

        <aside className="verdict-panel" aria-labelledby="verdict-heading">
          <div className="verdict-panel-head">
            <h2 id="verdict-heading">Today&rsquo;s drift verdict</h2>
            <span className="tag tag-mono">rule {drift.verdict.rule}</span>
          </div>
          <VerdictCard drift={drift} />
        </aside>
      </header>

      <section className="section" id="forecast">
        <div className="section-head">
          <span className="section-kicker">01</span>
          <h2>Forecast explorer</h2>
        </div>
        <p className="section-note">
          The day-ahead forecast against the demand that later arrived. Right of the{" "}
          <strong>now</strong> divider is the live forecast — hours whose actuals do not exist
          yet, which is exactly the region the drift monitor will score tomorrow.
        </p>
        <Card
          title="Actual vs forecast"
          note={forecast.note}
          aside={<span className="tag tag-mono">horizon ≤ {forecast.horizon_shown_h}h</span>}
        >
          <ForecastChart forecast={forecast} tokens={tokens} />
          <div className="card-foot">
            <span>Timezone: UTC</span>
            <span>Units: {forecast.units}</span>
            <span>
              One published series per target hour (largest horizon within 24 h) — per-horizon
              error is measured in the backtest, section 03.
            </span>
          </div>
        </Card>
      </section>

      <section className="section" id="drift">
        <div className="section-head">
          <span className="section-kicker">02</span>
          <h2>Drift monitoring</h2>
        </div>
        <p className="section-note">
          A model is fitted on the world as it was; then the world moves. Drift here is measured
          from <strong>the end of the champion&rsquo;s training data</strong>
          {trainEnd ? <> ({shortDateTime(trainEnd)} UTC)</> : null}, not from a sliding calendar
          window — so a model retrained this morning starts at zero by construction rather than
          by luck, and every signal below asks the same question: has anything meaningful
          happened since the model stopped learning?
        </p>

        <div className="stats">
          <Stat
            label="MAE, current window"
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
            label="MAPE, current window"
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
            value={
              monitor.severity === "ok" ? "Stable" : monitor.severity === "warn" ? "Warning" : "Alert"
            }
            sub="measured by a model that trained on neither window"
          />
        </div>

        <Card
          title="Drift by feature"
          note={
            drift.drift.feature?.columns?.length ? (
              <>
                {drift.drift.feature.summary} Greyed dots are deterministic calendar columns —
                reported, but excluded from the verdict, because their PSI measures which dates
                the windows cover rather than the data. Dots rather than bars on purpose: PSI
                spans orders of magnitude, and a bar length measured from a log axis&rsquo;
                minimum would lie.
              </>
            ) : undefined
          }
          aside={
            <span className="tag tag-mono">
              PSI warn {drift.thresholds.psi_warn} · alert {drift.thresholds.psi_alert}
            </span>
          }
        >
          {drift.drift.feature?.columns?.length ? (
            <FeaturePsiChart drift={drift} tokens={tokens} />
          ) : (
            <EmptyPanel
              title="Nothing to measure yet — and the artifact says so"
              reason={drift.reason ?? undefined}
            >
              {drift.verdict.rationale}
            </EmptyPanel>
          )}
        </Card>

        <div className="card-grid">
          <Card
            title="Drift over time"
            note={
              drift.timeline?.points?.length
                ? drift.timeline.description
                : "PSI of a trailing window against the reference, one point per day, once post-training data exists."
            }
          >
            {drift.timeline?.points?.length ? (
              <DriftTimelineChart drift={drift} tokens={tokens} />
            ) : (
              <EmptyPanel
                title="No drift timeline yet"
                reason={drift.timeline?.description ?? undefined}
              >
                The timeline accumulates one point per daily run, starting from the first run
                after the champion&rsquo;s training data ends. It restarts by design after every
                retrain — an empty state here means the model is younger than the data, not that
                monitoring is off.
              </EmptyPanel>
            )}
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
        </div>
      </section>

      <section className="section" id="model">
        <div className="section-head">
          <span className="section-kicker">03</span>
          <h2>Model vs baseline</h2>
        </div>
        <p className="section-note">
          {model.backtest.protocol}: <strong>{model.backtest.folds} refits</strong> over{" "}
          <strong>{model.backtest.weeks} weeks</strong> (
          {shortDateTime(model.backtest.first_cutoff_utc)} →{" "}
          {shortDateTime(model.backtest.last_cutoff_utc)} UTC), each scored on the next 24 hours,
          never on data the model had seen. The baseline —{" "}
          {model.models.baseline.description} — runs on identical folds, so the comparison is
          like for like. For scale, published day-ahead errors for large ISOs sit around 2–3%
          MAPE; this window is a summer one, the easier half of the year, and eight weeks is a
          short evidence base. Both are stated rather than smoothed over.
        </p>

        <Card
          title="Error by forecast horizon"
          aside={
            <span className="tag tag-mono">
              {model.metrics.comparison.horizons_won}/{model.metrics.comparison.horizons_total}{" "}
              horizons won
            </span>
          }
        >
          <HorizonChart model={model} tokens={tokens} />
          <div className="card-foot">
            <span>
              Overall: model MAE{" "}
              {model.metrics.lightgbm.overall.mae == null
                ? "—"
                : compact.format(model.metrics.lightgbm.overall.mae)}{" "}
              MWh vs baseline{" "}
              {model.metrics.baseline.overall.mae == null
                ? "—"
                : compact.format(model.metrics.baseline.overall.mae)}{" "}
              MWh ({precise.format(model.metrics.comparison.mae_delta_pct)}%).
            </span>
          </div>
        </Card>

        <div className="card-grid">
          <AblationCard model={model} />
          <Card
            title="Where the model looks"
            note={
              <>
                LightGBM gain share per feature, from the training run
                {model.feature_importance_gain_pct?.length ? (
                  <>
                    {" "}
                    — led by <code>{model.feature_importance_gain_pct[0].feature}</code>
                  </>
                ) : null}
                .
              </>
            }
          >
            <ImportanceChart model={model} tokens={tokens} />
          </Card>
        </div>

        {model.registry ? (
          <p className="section-note">
            Champion: <code>{model.registry.registered_model ?? "—"}</code> v
            {model.registry.version ?? "—"} <code>@{model.registry.alias ?? "champion"}</code>,
            promoted only because it beat the baseline on this same backtest. The MLflow registry
            backend is local run state; <code>metrics/*.json</code> is the only published surface
            — what you are reading is it.
          </p>
        ) : null}
      </section>

      <section className="section" id="loop">
        <div className="section-head">
          <span className="section-kicker">04</span>
          <h2>The loop</h2>
        </div>
        <p className="section-note">
          A scheduled job runs every morning at 06:20 UTC: it re-ingests, re-scores, re-runs the
          drift detectors and republishes every number on this page through a pull request —
          drift accumulates in public. The artifacts publish the latest run; the run-by-run
          history is the repository&rsquo;s{" "}
          <a href={`${REPO_URL}/pulls?q=is%3Apr`}>pull-request trail</a>.
        </p>

        <Card
          title="Latest run"
          aside={
            <span className="tag tag-mono">
              {pipeline.status} · {pipeline.seconds.toFixed(1)}s
            </span>
          }
          note={
            <>
              <code>{pipeline.entrypoint}</code>, started{" "}
              {shortDateTime(pipeline.generated_at_utc)} UTC.
            </>
          }
        >
          <LoopStrip steps={pipeline.steps} />
          <div className="card-foot">
            <span>
              Published artifacts: {pipeline.artifacts.filter((a) => a.endsWith(".json")).length}{" "}
              JSON + {pipeline.artifacts.filter((a) => !a.endsWith(".json")).length} static
            </span>
            <span>Schedule: daily 06:20 UTC (GitHub Actions cron)</span>
            {pipeline.error ? <span className="mono-note">error: {pipeline.error}</span> : null}
          </div>
        </Card>

        <HowItWasMade model={model} served={served?.version ?? null} />
      </section>
      </main>

      <footer className="footer">
        <div className="footer-grid">
          <div>
            <h3>Data</h3>
            <p>
              Demand from the{" "}
              <a href="https://www.eia.gov/opendata/">U.S. Energy Information Administration</a>
              {model.data.panel ? (
                <>
                  {" "}
                  — {compact.format(model.data.panel.rows)} hourly rows,{" "}
                  {shortDateTime(model.data.panel.start_utc)} →{" "}
                  {shortDateTime(model.data.panel.end_utc)} UTC
                </>
              ) : null}
              .
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
              aggregated to hourly features and scored, not shown raw.
            </p>
          </div>
          <div>
            <h3>Model</h3>
            <p>
              {served ? (
                <>
                  Serving <code>{served.uri ?? "champion"}</code>
                  {served.version ? <> (v{served.version})</> : null}
                  {trainEnd ? <>, trained through {shortDateTime(trainEnd)} UTC</> : null}.
                </>
              ) : (
                "No served model recorded on this run."
              )}
            </p>
            <p>
              Monitoring windows: reference {shortDateTime(drift.windows.reference_start_utc)} →{" "}
              {shortDateTime(drift.windows.current_start_utc)} (
              {compact.format(drift.windows.rows.reference)} rows), current{" "}
              {shortDateTime(drift.windows.current_start_utc)} →{" "}
              {shortDateTime(drift.windows.panel_end_utc)} (
              {compact.format(drift.windows.rows.current)} rows).
            </p>
          </div>
          <div>
            <h3>Site</h3>
            <p>
              A static page over <code>metrics/*.json</code> — the charts fetch the same files
              the pipeline commits, at runtime. Nothing on this page is typed in by hand.
            </p>
            <p>
              <a href={REPO_URL}>Source on GitHub</a> · artifacts refreshed{" "}
              {shortDateTime(pipeline.generated_at_utc)} UTC
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}

/**
 * The four headline numbers, straight from `model.json`. A missing field
 * renders as an em dash with an honest sub-line, never as a plausible value.
 */
export function KpiRow({ model }: { model: ModelArtifact }) {
  const lgbm = model.metrics.lightgbm.overall;
  const baseline = model.metrics.baseline.overall;
  const comparison = model.metrics.comparison;
  const ablation = model.ablation?.forecast_weather;
  const weatherMeasured =
    ablation?.measured === true && ablation.helped && ablation.mae_delta_pct != null;

  return (
    <div className="kpis">
      <Kpi
        label="Forecast error"
        value={lgbm.mape_pct == null ? "—" : precise.format(lgbm.mape_pct)}
        unit={lgbm.mape_pct == null ? undefined : "%"}
        sub={`MAPE over ${model.backtest.weeks} weeks · ${model.backtest.folds} walk-forward refits`}
        accent="var(--series-2)"
      />
      <Kpi
        label="vs baseline"
        value={`${comparison.mae_delta_pct.toFixed(0)}%`}
        sub={`MAE against ${model.models.baseline.description}${baseline.mape_pct == null ? "" : ` (${precise.format(baseline.mape_pct)}% MAPE)`}`}
        accent="var(--series-1)"
      />
      <Kpi
        label="Horizons won"
        value={`${comparison.horizons_won}/${comparison.horizons_total}`}
        sub={
          comparison.horizons_won === comparison.horizons_total
            ? "beats the baseline at every hour ahead"
            : "hours ahead where the model beats the baseline"
        }
        accent="var(--series-3)"
      />
      <Kpi
        label="Weather features"
        value={weatherMeasured ? `${ablation.mae_delta_pct!.toFixed(0)}%` : "—"}
        sub={
          weatherMeasured
            ? "error when added — measured by removing them and refitting"
            : "ablation not measured on this run"
        }
        accent="var(--neutral-series)"
      />
    </div>
  );
}

/** The ablation, as the two numbers it actually is. */
export function AblationCard({ model }: { model: ModelArtifact }) {
  const ablation = model.ablation?.forecast_weather;

  if (!ablation?.measured) {
    return (
      <Card title="Forecast-weather ablation">
        <EmptyPanel title="Not measured on this run">
          The ablation refits the model without the forecast-weather columns on identical
          folds; this artifact does not carry that measurement.
        </EmptyPanel>
      </Card>
    );
  }

  return (
    <Card
      title="Forecast-weather ablation"
      note={
        ablation.protocol
          ? `${ablation.protocol}.`
          : "Identical folds and hyperparameters; only the columns differ."
      }
    >
      <div className="stats" style={{ marginBottom: 8 }}>
        <Stat
          label="MAE without them"
          value={
            ablation.mae_without_forecast_weather == null
              ? "—"
              : compact.format(ablation.mae_without_forecast_weather)
          }
          unit="MWh"
        />
        <Stat
          label="MAE with them"
          value={
            ablation.mae_with_forecast_weather == null
              ? "—"
              : compact.format(ablation.mae_with_forecast_weather)
          }
          unit="MWh"
          sub={
            ablation.mae_delta_pct == null
              ? undefined
              : `${precise.format(ablation.mae_delta_pct)}% error`
          }
        />
      </div>
      {ablation.removed?.length ? (
        <p className="card-note">
          Removed: {ablation.removed.map((c, i) => (
            <span key={c}>
              {i > 0 ? ", " : ""}
              <code>{c}</code>
            </span>
          ))}
          . These are <em>archived forecasts</em> — what the weather service predicted, masked by
          publication hour so the model only sees what was public at the time.
        </p>
      ) : null}
      {ablation.warning ? (
        <p className="card-note">
          <strong>From the artifact&rsquo;s own warning field:</strong> {ablation.warning}
        </p>
      ) : null}
    </Card>
  );
}

/**
 * How, as six decisions rather than six nouns — condensed to cards. Each stage
 * names the trap it avoids, because "walk-forward backtest" means nothing to a
 * reader who has not already lost a week to a leaking one.
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
          The model uses <em>forecast</em> weather — what would actually be available day-ahead.
          Each archived forecast carries the hour it became public, and a feature is null until
          then. The mask costs accuracy and buys the right to believe the number.
        </>
      ),
    },
    {
      step: "Model",
      title: "One LightGBM across all horizons",
      body: (
        <>
          Horizon is a feature rather than a model per hour, so all{" "}
          {model.backtest.horizons_h.length} share the same fit. Direct, not recursive: no
          feeding predictions back in and compounding their errors.
        </>
      ),
    },
    {
      step: "Backtest",
      title: `${model.backtest.folds} refits, none looking forward`,
      body: (
        <>
          Refit at each daily cutoff on data available up to that point, scored on the next 24
          hours. The baseline runs on identical folds, so the comparison is like for like.
        </>
      ),
    },
    {
      step: "Registry",
      title: "Promotion is conditional",
      body: (
        <>
          Runs and metrics go to MLflow. A model becomes <code>@champion</code>
          {served ? ` (currently v${served})` : ""} only if it beats the baseline, and it is
          tagged with the last hour of its training data — the tag the drift monitor anchors on.
        </>
      ),
    },
    {
      step: "Daily",
      title: "The loop runs itself",
      body: (
        <>
          A scheduled job re-ingests, re-scores, re-runs the drift detectors and opens a pull
          request with the refreshed numbers. This page is those files; nothing here is typed in
          by hand.
        </>
      ),
    },
  ];

  return (
    <>
      <h3 style={{ margin: "22px 0 10px", fontSize: 15 }}>How it was made</h3>
      <ol className="stages">
        {stages.map((stage, index) => (
          <li key={stage.step} className="stage">
            <div className="stage-mark">
              <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
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

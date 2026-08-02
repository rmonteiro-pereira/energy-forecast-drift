/**
 * The non-chart pieces: the honesty banner, cards, status chips, table views.
 *
 * The banner is the load-bearing one. `metrics/*.json` carries `is_real`, and
 * while it is false every number on this page is a seeded synthetic fixture. A
 * dashboard that renders those numbers without saying so is how fixture output
 * ends up in a screenshot captioned "PJM demand forecast", so the banner is the
 * first element on the page, it is driven by the flag rather than hardcoded, and
 * it changes shape (not just wording) between the two states.
 */

import { useState, type ReactNode } from "react";

import type { DriftArtifact, Severity, VerdictAction } from "./types";

const SEVERITY_CLASS: Record<Severity, string> = {
  ok: "status-ok",
  warn: "status-warn",
  alert: "status-alert",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  ok: "OK",
  warn: "Warning",
  alert: "Alert",
};

/** Status is a dot **plus** its word — never colour on its own. */
export function StatusDot({ severity }: { severity: Severity }) {
  return (
    <>
      <span className={`dot ${SEVERITY_CLASS[severity]}`} aria-hidden="true" />
      <span className="sr-label">{SEVERITY_LABEL[severity]}</span>
    </>
  );
}

export function severityLabel(severity: Severity): string {
  return SEVERITY_LABEL[severity];
}

/**
 * The banner. Driven entirely by `isReal`; there is no prop to override it.
 */
export function ProvenanceBanner({
  isReal,
  warning,
  dataKind,
  generatedAt,
}: {
  isReal: boolean;
  warning: string | null;
  dataKind: string;
  generatedAt: string;
}) {
  if (!isReal) {
    return (
      <section className="banner banner-synthetic" role="alert">
        <span className="banner-icon" aria-hidden="true">
          ⚠️
        </span>
        <div>
          <h2>Synthetic data — these are not real forecasts, and not a benchmark</h2>
          <p>
            Every number on this page was computed from a <strong>seeded synthetic
            fixture</strong> (<code>{dataKind}</code>), not from EIA demand data — this lake
            holds no real demand, so the pipeline fell back to the fixture and said so. The
            charts prove the pipeline runs end to end. They say nothing about PJM and must
            not be quoted.
          </p>
          {warning ? (
            <p style={{ fontStyle: "italic" }}>
              From the artifact’s own <code>warning</code> field: “{warning}”
            </p>
          ) : null}
          <p>
            The Open-Meteo weather leg <em>is</em> real. Set <code>EIA_API_KEY</code>, re-run
            <code>python -m ingest</code> and the pipeline, and everything flips to real data —
            this banner turns green on its own, because it reads the artifact rather than a
            hardcoded state.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="banner banner-real">
      <span className="banner-icon" aria-hidden="true">
        ✅
      </span>
      <div>
        <h2>Live data</h2>
        <p>
          Computed from real EIA demand (<code>{dataKind}</code>) and Open-Meteo weather, last
          refreshed <time dateTime={generatedAt}>{generatedAt}</time> UTC by the daily
          pipeline.
        </p>
      </div>
    </section>
  );
}

export function Card({
  title,
  note,
  aside,
  children,
}: {
  title: string;
  note?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <h3>{title}</h3>
        {aside}
      </div>
      {note ? <p className="card-note">{note}</p> : null}
      {children}
    </section>
  );
}

export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
}

/**
 * Chart + its table twin, toggled.
 *
 * Not decoration: a tooltip must never be the only way to read a value, and two
 * of the palette slots sit below 3:1 against the light surface, which obliges a
 * non-colour path to the same numbers.
 */
export function ChartWithTable<T>({
  chart,
  rows,
  columns,
  caption,
}: {
  chart: ReactNode;
  rows: T[];
  columns: Column<T>[];
  caption: string;
}) {
  const [showTable, setShowTable] = useState(false);

  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 6 }}>
        <button
          type="button"
          aria-pressed={showTable}
          onClick={() => setShowTable((current) => !current)}
        >
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {showTable ? (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">{caption}</caption>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key} scope="col">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column.key}>{column.render(row)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        chart
      )}
    </>
  );
}

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

/**
 * The verdict, in whichever of its two shapes the artifact is in.
 *
 * It lives here rather than inline in `App` so it can be tested without
 * mounting the charts, and the branch is worth testing: collapsing these two
 * states is what once printed "Retrain" over a model that had been trained
 * that same morning. When `measurable` is false the champion's training data
 * reaches the end of the panel, so there is no window on the far side of it to
 * compare against — and the honest render says that rather than computing a
 * verdict from windows the model already learned.
 *
 * `measurable !== false` rather than a truthiness check on purpose: artifacts
 * written before the field existed have no opinion, and for those the answer is
 * "measured", not "unknown".
 */
export function VerdictCard({ drift }: { drift: DriftArtifact }) {
  const verdict = drift.verdict;
  const measurable = drift.measurable !== false;

  if (!measurable) {
    return (
      <div className="verdict">
        <div className="verdict-headline">
          <span className="dot status-ok" style={{ width: 14, height: 14 }} aria-hidden="true" />
          <div>
            <div className="verdict-figure">Not measurable yet</div>
            <div className="verdict-rule">should_retrain = false</div>
          </div>
        </div>
        <p className="card-note" style={{ margin: 0, maxWidth: "52ch" }}>
          The champion was trained through the end of the available data, so no hour has arrived
          yet that it did not learn from — and drift is the difference between those two. This is
          what every run looks like straight after a retrain. Forecast accuracy is unaffected and
          is still measured; the charts below are today&rsquo;s.
          {drift.reason ? (
            <>
              {" "}
              <span className="mono-note">{drift.reason}</span>
            </>
          ) : null}
        </p>
      </div>
    );
  }

  const action = ACTION_COPY[verdict.action];
  const severityClass =
    verdict.action === "retrain" ? "alert" : verdict.action === "watch" ? "warn" : "ok";

  return (
    <>
      <div className="verdict">
        <div className="verdict-headline">
          <span
            className={`dot status-${severityClass}`}
            style={{ width: 14, height: 14 }}
            aria-hidden="true"
          />
          <div>
            <div className="verdict-figure">{action.title}</div>
            <div className="verdict-rule">should_retrain = {String(verdict.should_retrain)}</div>
          </div>
        </div>
        <p className="card-note" style={{ margin: 0, maxWidth: "48ch" }}>
          {action.blurb}
        </p>
      </div>

      <div className="signals">
        {Object.entries(verdict.signals).map(([name, severity]) => (
          <div className="signal" key={name}>
            <div className="signal-head">
              <StatusDot severity={severity} />
              <span>{name}</span>
            </div>
            <p className="signal-detail">{drift.drift[name]?.summary ?? ""}</p>
          </div>
        ))}
      </div>
    </>
  );
}

export function Stat({
  label,
  value,
  unit,
  sub,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {value}
        {unit ? <span className="stat-unit">{unit}</span> : null}
      </div>
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}

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

import type { Severity } from "./types";

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
            fixture</strong> (<code>{dataKind}</code>), not from EIA demand data. The EIA API
            key has not been registered yet, so there is no real demand history in the lake.
            The charts prove the pipeline runs end to end. They say nothing about PJM and must
            not be quoted.
          </p>
          {warning ? (
            <p style={{ fontStyle: "italic" }}>
              From the artifact’s own <code>warning</code> field: “{warning}”
            </p>
          ) : null}
          <p>
            The Open-Meteo weather leg <em>is</em> real. Everything flips to real data — and
            this banner turns green — the moment the key lands and the pipeline is re-run.
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

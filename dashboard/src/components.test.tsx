/**
 * The banner is the honesty mechanism of this whole repository, so it gets a test
 * rather than a promise.
 *
 * The claim under test is narrow and load-bearing: `ProvenanceBanner` decides what
 * it renders from the `is_real` field of the artifact and from nothing else. Not
 * from a build flag, not from an environment variable, not from a prop a future
 * refactor could set to `true` to make a screenshot look better. If someone
 * "simplifies" the banner into a constant, or wires it to anything other than the
 * data, these tests fail.
 *
 * The two states are asserted to differ in *substance*, not in wording — a
 * different `role`, a different heading, and the presence or absence of the word
 * "benchmark" — so a cosmetic copy edit cannot quietly turn the warning into
 * decoration.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProvenanceBanner, VerdictCard } from "./components";
import type { DriftArtifact } from "./types";

afterEach(cleanup);

/** The exact shape `drift.json` presents while the EIA key is missing. */
const SYNTHETIC = {
  isReal: false,
  warning:
    "These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. " +
    "They are NOT a benchmark.",
  dataKind: "synthetic_fixture",
  generatedAt: "2026-07-28T06:00:00+00:00",
} as const;

/** The same artifact after a real backfill: only `is_real` and friends change. */
const REAL = {
  isReal: true,
  warning: null,
  dataKind: "eia_api_v2",
  generatedAt: "2026-07-28T06:00:00+00:00",
} as const;

describe("ProvenanceBanner", () => {
  it("shouts when the artifact says the data is synthetic", () => {
    render(<ProvenanceBanner {...SYNTHETIC} />);

    // role="alert" is the machine-readable half of "unmissable": it is announced
    // by a screen reader without the user going looking for it.
    const banner = screen.getByRole("alert");
    expect(banner.className).toContain("banner-synthetic");

    expect(
      screen.getByRole("heading", { name: /synthetic data/i }),
    ).toBeDefined();

    // The two words a reviewer must not be able to miss.
    expect(banner.textContent).toMatch(/not a benchmark/i);
    expect(banner.textContent).toMatch(/seeded synthetic fixture/i);
    expect(banner.textContent).toMatch(/must\s+not be quoted/i);

    // It quotes the artifact's own warning field rather than a hardcoded string,
    // so the Python side owns the wording.
    expect(banner.textContent).toContain(SYNTHETIC.warning);

    // And it names the provenance the artifact reported.
    expect(banner.textContent).toContain("synthetic_fixture");
  });

  it("goes quiet only when the artifact itself says the data is real", () => {
    render(<ProvenanceBanner {...REAL} />);

    // Substantively different, not just reworded: no alert role at all.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("heading", { name: /live data/i })).toBeDefined();
    expect(document.body.textContent).not.toMatch(/synthetic/i);
    expect(document.body.textContent).not.toMatch(/benchmark/i);
    expect(document.body.textContent).toContain("eia_api_v2");
  });

  it("is driven by the flag alone — same numbers, same props, different flag", () => {
    // Identical artifact in every respect except `is_real`. This is the exact
    // demonstration described in dashboard/README.md, executed rather than
    // described: nothing but the flag moves, and the banner changes state.
    const shared = { warning: null, dataKind: "eia_api_v2", generatedAt: REAL.generatedAt };

    const { unmount } = render(<ProvenanceBanner isReal={false} {...shared} />);
    expect(screen.getByRole("alert")).toBeDefined();
    unmount();

    render(<ProvenanceBanner isReal={true} {...shared} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("still warns when the artifact carries no warning text", () => {
    // A missing `warning` field must not be able to silence the banner: the flag
    // is the trigger, the warning string is only extra detail.
    render(<ProvenanceBanner {...SYNTHETIC} warning={null} />);

    const banner = screen.getByRole("alert");
    expect(banner.textContent).toMatch(/not a benchmark/i);
    expect(banner.textContent).toMatch(/seeded synthetic fixture/i);
  });
});

/**
 * The verdict card, which has to be wrong in only one direction.
 *
 * On 2026-08-02 this page showed "Retrain" over a champion that had been
 * trained hours earlier, because the monitoring windows slid with the wall
 * clock and both of them lay inside that champion's own training data. The
 * Python side now anchors on the end of training and publishes
 * `measurable: false` when nothing has arrived since; these assert the page
 * actually renders that state rather than falling through to a verdict.
 */
function driftArtifact(overrides: Partial<DriftArtifact> = {}): DriftArtifact {
  return {
    generated_at_utc: "2026-08-02T06:20:00+00:00",
    is_real: true,
    warning: null,
    verdict: {
      should_retrain: true,
      action: "retrain",
      severity: "alert",
      rule: "R1_performance_alert",
      rationale: "The rolling error crossed the degradation alert line.",
      signals: { feature: "alert", target: "ok", prediction: "alert", performance: "alert" },
      reasons: [],
      evaluated_at_utc: "2026-08-02T06:20:00+00:00",
    },
    thresholds: { psi_warn: 0.1, psi_alert: 0.2, mae_degradation_alert: 0.25 },
    windows: {
      reference_start_utc: "2026-07-05T01:00:00+00:00",
      current_start_utc: "2026-07-19T01:00:00+00:00",
      panel_end_utc: "2026-08-02T01:00:00+00:00",
      rows: { train: 1000, reference: 500, current: 500 },
    },
    data: { kind: "eia_api_v2", is_real: true },
    drift: {},
    ...overrides,
  } as DriftArtifact;
}

describe("VerdictCard", () => {
  it("shows the verdict when the artifact measured one", () => {
    render(<VerdictCard drift={driftArtifact()} />);

    expect(document.body.textContent).toContain("Retrain");
    expect(document.body.textContent).toContain("should_retrain = true");
    // Every signal the artifact carries is rendered, not just the worst.
    for (const name of ["feature", "target", "prediction", "performance"]) {
      expect(document.body.textContent).toContain(name);
    }
  });

  it("refuses to print a verdict when the champion is younger than the data", () => {
    render(
      <VerdictCard
        drift={driftArtifact({
          measurable: false,
          reason:
            "only 1 scored row(s) have arrived since the champion stopped learning at " +
            "2026-08-02T00:00:00+00:00; 200 are needed to measure drift.",
          verdict: {
            ...driftArtifact().verdict,
            should_retrain: false,
            action: "none",
            severity: "ok",
            rule: "R0_champion_is_current",
            rationale: "The champion was trained through the end of the available data.",
            signals: {},
          },
        })}
      />,
    );

    expect(document.body.textContent).toContain("Not measurable yet");
    expect(document.body.textContent).toContain("should_retrain = false");
    // The bug this exists to prevent, asserted as an absence.
    expect(document.body.textContent).not.toMatch(/\bRetrain\b/);
    // It says *why*, quoting the artifact rather than a hardcoded sentence.
    expect(document.body.textContent).toMatch(/only 1 scored row/);
  });

  it("treats an artifact with no `measurable` field as measured", () => {
    // Older artifacts predate the field. Absent means "this run measured drift",
    // not "unknown" — reading it as falsy would blank the card on every one of
    // them, which is a silent regression rather than a visible one.
    const legacy = driftArtifact();
    expect("measurable" in legacy).toBe(false);

    render(<VerdictCard drift={legacy} />);
    expect(document.body.textContent).toContain("Retrain");
    expect(document.body.textContent).not.toContain("Not measurable yet");
  });
});

/**
 * The v2 surfaces, tested for the property that matters: every number on the
 * page comes from the artifact it claims to come from, and a missing field
 * degrades honestly instead of falling back to something plausible.
 *
 * The fixtures use deliberately *wrong-looking* numbers (3.21% MAPE, -66%,
 * 21/24) precisely so a hardcoded "2.72" or "24/24" anywhere in the components
 * would fail these assertions.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AblationCard, KpiRow } from "./App";
import { EmptyPanel, LiveBadge, LoopStrip } from "./components";
import type { ModelArtifact, PipelineStep } from "./types";

afterEach(cleanup);

function modelArtifact(overrides: Partial<ModelArtifact> = {}): ModelArtifact {
  return {
    generated_at_utc: "2026-08-02T01:39:07+00:00",
    is_real: true,
    warning: null,
    models: {
      baseline: { name: "seasonal_naive_168h", description: "demand at the same hour, 7 days earlier" },
      challenger: {
        name: "lightgbm_global_direct",
        description: "one global LightGBM",
        n_features: 27,
        num_boost_round: 300,
        refits: 55,
      },
    },
    data: { kind: "eia_api_v2", respondent: "PJM" },
    backtest: {
      protocol: "walk-forward, daily cutoffs, no temporal leakage",
      weeks: 8,
      folds: 55,
      horizons_h: [1, 2, 3],
      first_cutoff_utc: "2026-06-07T12:00:00+00:00",
      last_cutoff_utc: "2026-07-31T12:00:00+00:00",
    },
    metrics: {
      baseline: { overall: { n: 100, mae: 13359, mape_pct: 11.73, rmse: 16862, bias: -1750 } },
      lightgbm: { overall: { n: 100, mae: 3050, mape_pct: 3.21, rmse: 3863, bias: -1096 } },
      comparison: {
        mae_delta: -10310,
        mae_delta_pct: -66.4,
        mape_delta_pct_points: -9.01,
        horizons_won: 21,
        horizons_total: 24,
      },
    },
    ablation: {
      forecast_weather: {
        measured: true,
        removed: ["fcst_temperature_c"],
        mae_without_forecast_weather: 5159.56,
        mae_with_forecast_weather: 3049.79,
        mae_delta_pct: -37.2,
        helped: true,
        warning: null,
      },
    },
    ...overrides,
  } as ModelArtifact;
}

describe("KpiRow", () => {
  it("renders exactly the artifact's numbers, not memorised ones", () => {
    render(<KpiRow model={modelArtifact()} />);

    expect(document.body.textContent).toContain("3.21"); // MAPE from the fixture
    expect(document.body.textContent).toContain("-66%"); // rounded delta from the fixture
    expect(document.body.textContent).toContain("21/24"); // horizons from the fixture
    expect(document.body.textContent).toContain("-37%"); // ablation from the fixture
    // The README's real numbers must NOT appear — they would mean a hardcode.
    expect(document.body.textContent).not.toContain("2.72");
    expect(document.body.textContent).not.toContain("24/24");
  });

  it("does not claim a clean sweep unless the artifact says so", () => {
    render(<KpiRow model={modelArtifact()} />);
    // 21/24 in the fixture: the sub-line must hedge, not brag.
    expect(document.body.textContent).not.toMatch(/every hour ahead/i);
  });

  it("degrades the ablation tile to an em dash when it was not measured", () => {
    const model = modelArtifact();
    model.ablation = { forecast_weather: { measured: false, mae_delta_pct: null, helped: false, warning: null } };
    render(<KpiRow model={model} />);

    expect(document.body.textContent).toContain("ablation not measured on this run");
    expect(document.body.textContent).not.toContain("-37%");
  });
});

describe("AblationCard", () => {
  it("shows both MAE figures and the removed columns from the artifact", () => {
    render(<AblationCard model={modelArtifact()} />);

    expect(document.body.textContent).toContain("5,160"); // without, compact-formatted
    expect(document.body.textContent).toContain("3,050"); // with
    expect(document.body.textContent).toContain("fcst_temperature_c");
  });

  it("surfaces the artifact's own warning where the number appears", () => {
    const model = modelArtifact();
    model.ablation!.forecast_weather!.warning =
      "ABLATION MEASURED ON THE SYNTHETIC FIXTURE — not evidence about PJM.";
    render(<AblationCard model={model} />);

    expect(document.body.textContent).toContain(
      "ABLATION MEASURED ON THE SYNTHETIC FIXTURE — not evidence about PJM.",
    );
  });

  it("renders the honest empty state when the ablation was not measured", () => {
    const model = modelArtifact();
    model.ablation = undefined;
    render(<AblationCard model={model} />);

    expect(document.body.textContent).toContain("Not measured on this run");
    expect(document.body.textContent).not.toContain("5,160");
  });
});

describe("LiveBadge", () => {
  it("is driven by is_real and by nothing else", () => {
    const { unmount } = render(<LiveBadge isReal={true} />);
    expect(screen.getByText("Live data")).toBeDefined();
    unmount();

    render(<LiveBadge isReal={false} />);
    expect(screen.getByText("Synthetic data")).toBeDefined();
  });
});

describe("EmptyPanel", () => {
  it("quotes the artifact's reason verbatim rather than paraphrasing it", () => {
    const reason =
      "only 172 scored row(s) have arrived since the champion stopped learning at " +
      "2026-08-02T00:00:00+00:00; 200 are needed to measure drift.";
    render(
      <EmptyPanel title="Nothing to measure yet" reason={reason}>
        The champion was trained through the end of the available data.
      </EmptyPanel>,
    );

    expect(document.body.textContent).toContain(reason);
    expect(document.body.textContent).toContain("Nothing to measure yet");
  });
});

describe("LoopStrip", () => {
  const steps: PipelineStep[] = [
    { step: "ingest", status: "ok", seconds: 10.71 },
    { step: "features", status: "ok", seconds: 0.36 },
    { step: "score", status: "failed", seconds: 7.69 },
  ];

  it("renders every step the pipeline recorded, with its duration", () => {
    render(<LoopStrip steps={steps} />);

    for (const s of ["ingest", "features", "score"]) {
      expect(document.body.textContent).toContain(s);
    }
    expect(document.body.textContent).toContain("10.7s");
  });

  it("shows a failure as a failure, not as a green tick", () => {
    render(<LoopStrip steps={steps} />);
    expect(document.body.textContent).toContain("failed");
  });
});

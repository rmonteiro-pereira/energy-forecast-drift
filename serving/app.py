"""`GET /forecast` — the registry champion, served.

    uv run python -m serving            # http://127.0.0.1:8000/docs
    curl 'http://127.0.0.1:8000/forecast?max_horizon=6'

Two things this deliberately does *not* do
------------------------------------------
**It does not hardcode a model path.** The booster comes from
`models:/energy-demand-forecaster@champion` — an alias in the MLflow registry.
Promoting a challenger is then a registry operation; nothing here is
redeployed, and `/model` reports which version actually answered.

**It does not pretend a fixture is data.** The `is_real` flag travels with the
model (stamped on the training run) and with the panel, and every response
carries both plus the synthetic warning when either is false. An endpoint that
returns plausible MWh numbers with no provenance is exactly how fixture output
ends up in a screenshot.

Feature parity with training is not re-implemented here: the request is turned
into rows by the same `features.build.build_design_matrix` that produced the
training matrix, so a feature can never be computed one way for fitting and
another way for serving.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

import lightgbm as lgb
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query

from features import build as build_mod
from features import panel as panel_mod
from models import lgbm as lgbm_mod
from models import tracking
from models.data import SYNTHETIC_WARNING, resolve_panel

log = logging.getLogger("serving")

MAX_HORIZON = 24
DEFAULT_NUM_BOOST_ROUND = lgbm_mod.DEFAULT_NUM_BOOST_ROUND

# Fallback used when the registry has no champion yet (a fresh clone, or CI).
# It is a real fit on the same panel, not a stub — but it is labelled as a
# fallback in every response so nobody mistakes it for the promoted model.
FALLBACK_SOURCE = "fallback_fit"


@dataclass
class ForecastService:
    """Panel + booster, loaded once and reused across requests.

    The panel is loaded eagerly at first use rather than per request: building
    it re-reads the lake and re-derives the calendar, which is milliseconds of
    work repeated for no reason on a series that changes once a day.
    """

    source: str = "auto"
    fixture_days: int = 200
    panel: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    provenance: dict = field(default_factory=dict)
    booster: lgb.Booster | None = field(default=None, repr=False)
    model_info: dict = field(default_factory=dict)

    def load(self) -> ForecastService:
        self.panel, self.provenance = resolve_panel(self.source, fixture_days=self.fixture_days)
        try:
            self.booster, self.model_info = tracking.load_champion()
        except tracking.ChampionUnavailable as exc:
            log.warning("No registry champion (%s) — fitting a fallback booster.", exc)
            self.booster, _design = lgbm_mod.fit_final(self.panel)
            self.model_info = {
                "source": FALLBACK_SOURCE,
                "uri": None,
                "alias": None,
                "version": None,
                "reason": str(exc),
                "trained_on_real_data": self.provenance.get("is_real", False),
                "data_kind": self.provenance.get("kind"),
                "n_features": int(self.booster.num_feature()),
            }
        return self

    # -- provenance ---------------------------------------------------------
    @property
    def is_real(self) -> bool:
        """True only when *both* the panel and the model come from real data."""
        return bool(self.provenance.get("is_real")) and bool(
            self.model_info.get("trained_on_real_data")
        )

    @property
    def warning(self) -> str | None:
        return None if self.is_real else SYNTHETIC_WARNING

    @property
    def latest_origin(self) -> pd.Timestamp:
        """The most recent hour with an observed demand value.

        Forecasting from a later origin would need features the lake does not
        have yet, so this is the honest edge of the information set.
        """
        observed = self.panel[panel_mod.DEMAND_COLUMN].dropna()
        if observed.empty:
            raise HTTPException(503, "The panel holds no observed demand to forecast from.")
        return observed.index.max() + pd.Timedelta(hours=1)

    @property
    def earliest_origin(self) -> pd.Timestamp:
        """The first origin with enough history behind it for the features to exist."""
        return self.panel.index.min() + pd.Timedelta(hours=build_mod.MIN_HISTORY_HOURS)

    def _validate_origin(self, origin: pd.Timestamp) -> None:
        """Refuse origins the panel cannot actually support.

        `build_design_matrix` does not refuse them — it emits NaN features, which
        LightGBM consumes happily and turns into a confident-looking number. A
        forecast built on no history at all is worse than an error, so the bound
        is enforced here rather than left to the model.
        """
        if origin < self.earliest_origin:
            raise HTTPException(
                422,
                f"Origin {origin.isoformat()} has less than "
                f"{build_mod.MIN_HISTORY_HOURS}h of history behind it. The earliest "
                f"origin this panel supports is {self.earliest_origin.isoformat()}.",
            )
        if origin > self.latest_origin:
            raise HTTPException(
                422,
                f"Origin {origin.isoformat()} is beyond the information set — the last "
                f"observed hour supports origins up to {self.latest_origin.isoformat()}.",
            )

    @property
    def loaded_booster(self) -> lgb.Booster:
        """The booster, or an actionable 503 — never an `AttributeError`.

        `booster` is `None` until `load()` runs, and `load()` always leaves it
        set (registry champion, or a fallback fit). So this only fires if a
        `ForecastService` is used without being loaded, which is a wiring bug.
        Saying so beats `'NoneType' object has no attribute 'predict'` surfacing
        as a 500 with a stack trace and no clue in it.
        """
        if self.booster is None:  # pragma: no cover - guards a wiring mistake
            raise HTTPException(
                503,
                "The forecast service holds no model: ForecastService.load() was "
                "never called, or it failed. Check the startup logs.",
            )
        return self.booster

    # -- the actual work ----------------------------------------------------
    def forecast(self, origin: pd.Timestamp, max_horizon: int) -> dict:
        self._validate_origin(origin)

        horizons = tuple(range(1, max_horizon + 1))
        design = build_mod.build_design_matrix(self.panel, pd.DatetimeIndex([origin]), horizons)
        if design.empty:  # pragma: no cover - unreachable once the origin is validated
            raise HTTPException(422, f"No design row could be built at {origin.isoformat()}.")

        predictions = self.loaded_booster.predict(build_mod.feature_frame(design))
        actual = design[build_mod.TARGET_COLUMN]

        rows = [
            {
                "horizon_h": int(row.horizon_h),
                "target_utc": pd.Timestamp(row.target_utc).isoformat(),
                "forecast_mwh": round(float(prediction), 1),
                # Present only for hours that have already happened; a forecast
                # endpoint that invents an actual is worse than one with a null.
                "actual_mwh": (None if pd.isna(row.y) else round(float(row.y), 1)),
            }
            for row, prediction, _ in zip(
                design.itertuples(index=False), predictions, actual, strict=True
            )
        ]

        return {
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "origin_utc": origin.isoformat(),
            "units": "MWh",
            "is_real": self.is_real,
            "warning": self.warning,
            "model": self.model_info,
            "data": {k: v for k, v in self.provenance.items() if k != "warning"},
            "horizons": len(rows),
            "forecast": rows,
        }


@lru_cache(maxsize=1)
def get_service() -> ForecastService:
    """Process-wide singleton, injected as a FastAPI dependency.

    A dependency rather than a module global so the tests can substitute a
    service built on the fixture (`app.dependency_overrides[get_service]`)
    without an MLflow database or a data lake having to exist.
    """
    return ForecastService().load()


# `Annotated[...]` rather than a `Depends(...)` default: the dependency becomes
# part of the type instead of a mutable default evaluated once at import.
Service = Annotated[ForecastService, Depends(get_service)]


def create_app() -> FastAPI:
    app = FastAPI(
        title="energy-forecast-drift",
        version="0.1.0",
        summary="Hourly electricity demand forecast from the MLflow registry champion.",
        description=__doc__,
    )

    @app.get("/health", tags=["ops"])
    def health(service: Service) -> dict:
        """Liveness plus the two facts that decide whether to trust a response."""
        return {
            "status": "ok",
            "model_source": service.model_info.get("source"),
            "model_version": service.model_info.get("version"),
            "is_real": service.is_real,
            "panel_rows": len(service.panel),
        }

    @app.get("/model", tags=["ops"])
    def model(service: Service) -> dict:
        """Which registry version is answering, and what it was trained on."""
        return {
            "model": service.model_info,
            "data": service.provenance,
            "is_real": service.is_real,
            "warning": service.warning,
        }

    @app.get("/forecast", tags=["forecast"])
    def forecast(
        service: Service,
        origin_utc: Annotated[
            str | None,
            Query(
                description=(
                    "Forecast origin (ISO-8601, UTC). Defaults to the first hour after "
                    "the last observed demand — the edge of the information set."
                )
            ),
        ] = None,
        max_horizon: Annotated[int, Query(ge=1, le=MAX_HORIZON)] = MAX_HORIZON,
    ) -> dict:
        """`max_horizon` hourly forecasts from `origin_utc`, champion-served."""
        if origin_utc is None:
            origin = service.latest_origin
        else:
            try:
                origin = pd.Timestamp(origin_utc)
            except ValueError as exc:
                raise HTTPException(422, f"Unparseable origin_utc: {origin_utc!r}") from exc
            origin = (
                origin.tz_localize("UTC") if origin.tzinfo is None else origin.tz_convert("UTC")
            )

        return service.forecast(origin.floor("h"), max_horizon)

    return app


app = create_app()

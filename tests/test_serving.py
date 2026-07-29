"""`/forecast` must return a forecast, and must never lie about where it came from.

The endpoint is exercised through FastAPI's `TestClient`, which drives the real
ASGI app — same routing, same validation, same serialisation as uvicorn — so
these are end-to-end tests of the HTTP surface without binding a port.

The provenance assertions carry as much weight as the numeric ones. An endpoint
that returns plausible MWh with no `is_real` flag is exactly how fixture output
ends up in a screenshot captioned "PJM demand forecast".
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import serving.app as app_mod
from features import panel as panel_mod
from models import fixtures, lgbm


@pytest.fixture(scope="module")
def service() -> app_mod.ForecastService:
    """A service wired to the fixture and a cheap booster — no registry, no lake.

    Built by hand rather than through `ForecastService.load()` so the tests do
    not depend on whether this machine happens to have an MLflow database with a
    promoted champion in it.
    """
    frame = fixtures.synthetic_series(days=90)
    panel = panel_mod.build_panel(frame["demand_mwh"], frame["temperature_c"])
    booster, _design = lgbm.fit_final(panel, num_boost_round=40, train_stride_hours=24)

    return app_mod.ForecastService(
        panel=panel,
        provenance={"kind": "synthetic_fixture", "is_real": False, "warning": "synthetic"},
        booster=booster,
        model_info={
            "source": "fallback_fit",
            "version": None,
            "trained_on_real_data": False,
            "n_features": int(booster.num_feature()),
        },
    )


@pytest.fixture(scope="module")
def client(service) -> TestClient:
    """The real ASGI app with the service dependency pointed at the fixture."""
    app = app_mod.create_app()
    app.dependency_overrides[app_mod.get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_reports_the_two_facts_that_decide_trust(client):
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["is_real"] is False
    assert payload["panel_rows"] > 0


def test_forecast_returns_one_row_per_horizon(client):
    response = client.get("/forecast", params={"max_horizon": 6})
    assert response.status_code == 200

    payload = response.json()
    assert payload["horizons"] == 6
    assert [row["horizon_h"] for row in payload["forecast"]] == [1, 2, 3, 4, 5, 6]
    assert all(row["forecast_mwh"] > 0 for row in payload["forecast"])
    assert payload["units"] == "MWh"


def test_forecast_targets_are_consecutive_hours_after_the_origin(client):
    payload = client.get("/forecast", params={"max_horizon": 5}).json()
    origin = pd.Timestamp(payload["origin_utc"])
    for row in payload["forecast"]:
        assert pd.Timestamp(row["target_utc"]) == origin + pd.Timedelta(hours=row["horizon_h"])


def test_every_response_carries_its_provenance(client):
    payload = client.get("/forecast", params={"max_horizon": 2}).json()
    assert payload["is_real"] is False
    assert "SYNTHETIC" in payload["warning"]
    assert payload["data"]["kind"] == "synthetic_fixture"
    assert payload["model"]["trained_on_real_data"] is False


def test_the_default_origin_is_the_edge_of_the_information_set(client, service):
    payload = client.get("/forecast").json()
    last_observed = service.panel[panel_mod.DEMAND_COLUMN].dropna().index.max()
    assert pd.Timestamp(payload["origin_utc"]) == last_observed + pd.Timedelta(hours=1)
    # Nothing after the last observed hour exists yet, so no actual may be filled in.
    assert all(row["actual_mwh"] is None for row in payload["forecast"])


def test_an_explicit_past_origin_comes_back_with_the_actuals(client, service):
    origin = service.panel.index.max() - pd.Timedelta(days=3)
    payload = client.get(
        "/forecast", params={"origin_utc": origin.isoformat(), "max_horizon": 4}
    ).json()

    assert pd.Timestamp(payload["origin_utc"]) == origin
    assert all(row["actual_mwh"] is not None for row in payload["forecast"])


def test_a_naive_origin_is_read_as_utc(client, service):
    origin = service.panel.index.max() - pd.Timedelta(days=3)
    naive = client.get(
        "/forecast", params={"origin_utc": origin.tz_localize(None).isoformat(), "max_horizon": 2}
    ).json()
    assert pd.Timestamp(naive["origin_utc"]) == origin


def test_the_horizon_is_bounded_by_the_model_not_by_the_caller(client):
    assert client.get("/forecast", params={"max_horizon": 25}).status_code == 422
    assert client.get("/forecast", params={"max_horizon": 0}).status_code == 422


def test_an_origin_before_the_feature_warm_up_is_refused_with_a_reason(client, service):
    """All-NaN features produce a confident-looking number; an error is better."""
    too_early = service.panel.index.min() + pd.Timedelta(hours=1)
    response = client.get("/forecast", params={"origin_utc": too_early.isoformat()})
    assert response.status_code == 422
    assert "history" in response.json()["detail"]
    assert service.earliest_origin.isoformat() in response.json()["detail"]


def test_an_origin_past_the_information_set_is_refused(client, service):
    beyond = service.panel.index.max() + pd.Timedelta(days=2)
    response = client.get("/forecast", params={"origin_utc": beyond.isoformat()})
    assert response.status_code == 422
    assert "information set" in response.json()["detail"]


def test_the_model_endpoint_names_the_version_that_answers(client):
    payload = client.get("/model").json()
    assert payload["model"]["source"] in {"mlflow_registry", "fallback_fit"}
    assert payload["is_real"] is False


def test_a_real_panel_with_a_fixture_model_is_still_not_real():
    """Both halves must be real. A fixture-trained champion keeps the run synthetic."""
    service = app_mod.ForecastService(
        provenance={"kind": "eia_api_v2", "is_real": True},
        model_info={"source": "mlflow_registry", "trained_on_real_data": False},
    )
    assert service.is_real is False
    assert service.warning is not None

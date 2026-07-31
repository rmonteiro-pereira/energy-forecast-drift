"""MLflow tracking + model registry, backed by a local sqlite file.

Why sqlite and not the default `./mlruns` file store: the **model registry**
does not exist on the file store. A registry is the point of M3 — it is what
lets serving ask for "whatever is champion right now" instead of hardcoding a
path — so the backend has to be a database. sqlite gives that for free, with no
server to run and nothing to pay for.

Both the database and the artifact directory are **gitignored and never
committed**. They are local run state, not a published artifact; the published
surface of this repo stays `metrics/*.json`. A test asserts the ignore rules.

Layout:
    mlflow.db   sqlite backend  — experiments, runs, params, metrics, registry
    mlruns/     artifact store  — the serialised booster, signature, env
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ingest.config import REPO_ROOT

log = logging.getLogger(__name__)

MLFLOW_DB = REPO_ROOT / "mlflow.db"
MLRUNS_DIR = REPO_ROOT / "mlruns"

EXPERIMENT_NAME = "energy-demand-forecast"
REGISTERED_MODEL_NAME = "energy-demand-forecaster"
CHAMPION_ALIAS = "champion"
CHALLENGER_ALIAS = "challenger"


def sqlite_uri(path: Path) -> str:
    """`sqlite:///...` URI for a filesystem path (POSIX-slashed, Windows-safe)."""
    return f"sqlite:///{Path(path).resolve().as_posix()}"


@dataclass(frozen=True)
class TrackingConfig:
    tracking_uri: str
    artifact_uri: str
    experiment_name: str
    experiment_id: str

    def as_dict(self) -> dict:
        return {
            "tracking_uri": self.tracking_uri,
            "artifact_uri": self.artifact_uri,
            "experiment": self.experiment_name,
            "experiment_id": self.experiment_id,
            "registered_model": REGISTERED_MODEL_NAME,
        }


def configure(
    tracking_db: Path = MLFLOW_DB,
    artifact_root: Path = MLRUNS_DIR,
    experiment_name: str = EXPERIMENT_NAME,
) -> TrackingConfig:
    """Point MLflow at the local sqlite backend and make sure the experiment exists."""
    import mlflow

    tracking_uri = sqlite_uri(tracking_db)
    artifact_root = Path(artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)

    existing = mlflow.get_experiment_by_name(experiment_name)
    if existing is None:
        experiment_id = mlflow.create_experiment(
            experiment_name, artifact_location=artifact_root.as_uri()
        )
    else:
        experiment_id = existing.experiment_id
    mlflow.set_experiment(experiment_name)

    return TrackingConfig(
        tracking_uri=tracking_uri,
        artifact_uri=artifact_root.as_uri(),
        experiment_name=experiment_name,
        experiment_id=str(experiment_id),
    )


def log_backtest(prefix: str, result) -> None:
    """Log one model's backtest: overall scalars + a metric per horizon.

    Per-horizon values use `step=horizon`, so MLflow's UI draws the error curve
    against forecast distance — the shape that actually matters for a forecaster.

    Sent as one batch: ~50 individual `log_metric` calls against sqlite are ~50
    transactions, which dominated the runtime of this step before it was fixed.
    """
    import mlflow
    from mlflow.entities import Metric

    run = mlflow.active_run()
    if run is None:  # pragma: no cover - misuse guard
        raise RuntimeError("log_backtest must be called inside an active MLflow run")

    stamp = int(time.time() * 1000)
    metrics = [
        Metric(key=f"{prefix}_{name}", value=float(value), timestamp=stamp, step=0)
        for name, value in result.overall.items()
    ]
    for row in result.by_horizon.itertuples(index=False):
        horizon = int(row.horizon_h)
        metrics.append(Metric(f"{prefix}_mae_by_h", float(row.mae), timestamp=stamp, step=horizon))
        metrics.append(
            Metric(f"{prefix}_mape_by_h", float(row.mape_pct), timestamp=stamp, step=horizon)
        )

    mlflow.MlflowClient().log_batch(run.info.run_id, metrics=metrics)


def _pip_requirements() -> list[str]:
    # Pinned explicitly: inferring them makes `log_model` walk the whole
    # environment, and the serving env only needs these three.
    return [
        f"lightgbm=={lgb.__version__}",
        f"pandas=={pd.__version__}",
        f"numpy=={np.__version__}",
    ]


def register_model(
    booster: lgb.Booster,
    features: pd.DataFrame,
    predictions: np.ndarray,
    *,
    tags: dict | None = None,
) -> str:
    """Log the booster as a run artifact and create a registry version."""
    import mlflow
    from mlflow.models import infer_signature

    info = mlflow.lightgbm.log_model(
        booster,
        name="model",
        signature=infer_signature(features, predictions),
        input_example=features.head(3),
        registered_model_name=REGISTERED_MODEL_NAME,
        pip_requirements=_pip_requirements(),
        metadata=tags or {},
    )
    version = _latest_version(info)
    log.info("Registered %s version %s", REGISTERED_MODEL_NAME, version)
    return version


def _latest_version(model_info) -> str:
    """The version just created — read back from the registry, not assumed."""
    import mlflow

    registered = getattr(model_info, "registered_model_version", None)
    if registered is not None:
        return str(registered)
    client = mlflow.MlflowClient()
    versions = client.search_model_versions(f"name='{REGISTERED_MODEL_NAME}'")
    return str(max(int(v.version) for v in versions))


def set_alias(version: str, alias: str) -> None:
    """Move a registry alias (`champion` / `challenger`) onto a version."""
    import mlflow

    mlflow.MlflowClient().set_registered_model_alias(REGISTERED_MODEL_NAME, alias, version)
    log.info("Alias @%s -> %s v%s", alias, REGISTERED_MODEL_NAME, version)


def champion_uri(alias: str = CHAMPION_ALIAS) -> str:
    """What serving loads — an alias, never a hardcoded path."""
    return f"models:/{REGISTERED_MODEL_NAME}@{alias}"


class ChampionUnavailable(RuntimeError):
    """No model carries the requested alias — or the registry is not there yet."""


def load_champion(
    alias: str = CHAMPION_ALIAS,
    tracking_db: Path = MLFLOW_DB,
) -> tuple[lgb.Booster, dict]:
    """Load the aliased model out of the registry, plus who it turned out to be.

    Serving and the daily pipeline both go through here, and both ask for an
    *alias* rather than a version: promoting a model then becomes a registry
    operation instead of a deploy. The metadata comes back with the booster so
    a response can say exactly which version answered it — a forecast whose
    provenance you cannot name is not much use in an incident.

    Raises `ChampionUnavailable` (never a bare MlflowException) so callers can
    fall back deliberately instead of catching everything.
    """
    import mlflow

    if not Path(tracking_db).exists():
        raise ChampionUnavailable(
            f"No MLflow database at {tracking_db}. Run `uv run python -m models.train` "
            "to create the registry and register a first version."
        )

    mlflow.set_tracking_uri(sqlite_uri(tracking_db))
    mlflow.set_registry_uri(sqlite_uri(tracking_db))
    uri = champion_uri(alias)

    try:
        client = mlflow.MlflowClient()
        version = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, alias)
        booster = mlflow.lightgbm.load_model(uri)
        # A registered version with no run behind it cannot carry the `is_real`
        # tag, and that tag is what stops a fixture-trained model being served as
        # though it were real. Refuse it by name rather than letting `get_run`
        # fail with a less specific message.
        if version.run_id is None:
            raise ChampionUnavailable(
                f"{uri} (version {version.version}) records no run_id, so its "
                "training provenance cannot be read. Re-register it with "
                "`uv run python -m models.train`."
            )
        run_tags = dict(client.get_run(version.run_id).data.tags or {})
    except ChampionUnavailable:
        raise
    except Exception as exc:
        raise ChampionUnavailable(
            f"Could not load {uri}: {type(exc).__name__}: {exc}. "
            "Run `uv run python -m models.train` to register and promote a model."
        ) from exc

    # The training run stamped `is_real` and `data_kind` from the panel
    # provenance, so a model fitted on the fixture cannot be served as if it
    # were real: the flag travels with the model, not with the caller's hopes.
    trained_on_real = run_tags.get("is_real", "false").lower() == "true"

    metadata = {
        "source": "mlflow_registry",
        "uri": uri,
        "registered_model": REGISTERED_MODEL_NAME,
        "alias": alias,
        "version": str(version.version),
        "run_id": version.run_id,
        "trained_on_real_data": trained_on_real,
        "data_kind": run_tags.get("data_kind"),
        # The last hour the model was allowed to learn from. `None` for versions
        # registered before this tag existed — consumers must treat that as
        # "unknown", never as "safe".
        "train_data_end_utc": run_tags.get("train_data_end_utc"),
        "n_features": int(booster.num_feature()),
    }
    return booster, metadata

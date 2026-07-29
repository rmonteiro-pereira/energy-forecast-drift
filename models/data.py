"""Where the modelling panel comes from — and what to stamp on it.

Both entrypoints (`python -m models` for the baseline, `python -m models.train`
for LightGBM + MLflow) resolve their data here so a single place decides whether
a run is real or synthetic, and so the `"is_real": false` flag and its warning
cannot drift apart between artifacts.
"""

from __future__ import annotations

import logging

import pandas as pd

from features import panel as panel_mod
from ingest.config import BALANCING_AUTHORITY, WEATHER_SITE
from models import fixtures

log = logging.getLogger(__name__)

SYNTHETIC_WARNING = (
    "These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. "
    "They are a smoke test of the pipeline, NOT a benchmark. The real baseline "
    "is pending the EIA API key — see docs/BLOCKED.md."
)


class NoRealDataError(RuntimeError):
    """Raised by `--source real` when the lake holds no EIA demand yet."""


def resolve_panel(source: str = "auto", fixture_days: int = 200) -> tuple[pd.DataFrame, dict]:
    """Return the modelling panel plus the provenance block for the artifact.

    `source`:
      * `real`      — the lake, or fail loudly;
      * `synthetic` — the seeded fixture, always;
      * `auto`      — the lake if it has anything, otherwise the fixture with a
        loud warning. This is what keeps the pipeline runnable while the EIA
        API key is pending (docs/BLOCKED.md).
    """
    if source in ("auto", "real"):
        demand = panel_mod.load_demand(BALANCING_AUTHORITY)
        if not demand.empty:
            temperature = panel_mod.load_temperature(WEATHER_SITE)
            panel = panel_mod.build_panel(demand, temperature)
            return panel, {
                "kind": "eia_api_v2",
                "is_real": True,
                "respondent": BALANCING_AUTHORITY,
                "weather_site": WEATHER_SITE,
                "warning": None,
            }

        if source == "real":
            raise NoRealDataError(
                "No EIA demand in the lake. Run `uv run python -m ingest` first "
                "(requires EIA_API_KEY — see docs/BLOCKED.md), or use "
                "`--source synthetic`."
            )
        log.warning("No real demand in the lake -> falling back to the SYNTHETIC fixture.")

    frame = fixtures.synthetic_series(days=fixture_days)
    panel = panel_mod.build_panel(frame["demand_mwh"], frame["temperature_c"])
    return panel, {
        "kind": "synthetic_fixture",
        "is_real": False,
        "generator": "models.fixtures.synthetic_series",
        "seed": fixtures.SEED,
        "anchor_end_utc": fixtures.ANCHOR_END.isoformat(),
        "label": fixtures.SYNTHETIC_LABEL,
        "warning": SYNTHETIC_WARNING,
    }

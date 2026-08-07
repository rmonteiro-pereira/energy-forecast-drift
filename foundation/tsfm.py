"""The Chronos-Bolt adapter — importable without torch, unusable without it.

The split is the whole design. `import foundation.tsfm` must leave
`sys.modules` free of torch, because the CI job installs `--extra dev` and
nothing else, and `pytest` fails at *collection* on a missing import while
`mypy` reports `Success` on the same file (`ignore_missing_imports = true`).
Two gates, opposite verdicts, and the pytest one is the loud one.

So torch and `chronos` are imported inside `load`, never at module scope, and a
test asserts that importing this module does not pull them in. That assertion is
G5's only honest half: the other two conditions — torch declared solely in the
`foundation` extra, and the CI sync line not requesting that extra — are true of
an empty repository too, and a gate with no reachable red state is decoration.

Nothing here downloads anything at import time either. The checkpoint is
34,622,352 bytes at its smallest, 6.6x the size ceiling, so it can never be
vendored; `load` fetches it and that call belongs to the dispatch run, not to CI.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

#: Pinned by revision, not by tag: a tag can be moved and the artifact records
#: what actually ran.
DEFAULT_REPO = "amazon/chronos-bolt-small"

#: Provenance of the weights, resolved from the Hugging Face API on 2026-08-06
#: and carried into the artifact so a reader can re-derive it instead of trusting
#: it. `sha256` comes from the LFS `X-Linked-ETag` header, which means it is the
#: hash of the file that *will* be downloaded, established without downloading
#: 190 MB.
#:
#: The two corpus fields exist because of the risk this lane cannot design away.
#: The fold window (2026-06-07 to 2026-07-31) postdates every released checkpoint,
#: so the target *values* cannot be memorised. That says nothing about the
#: *shape*: a daily-and-weekly electricity load profile is ordinary material in
#: these corpora, and "zero-shot" would be doing quiet work in a sentence that
#: ignored it.
#:
#: `energy_domain_in_corpus` is `undeclared` and not `yes`, and the distinction is
#: the point. What is established: the model card does not enumerate the corpus
#: at all; the Chronos paper's dataset appendix has a named `B.1 Energy`
#: subsection; and its Table 1 records Benchmark I as "pretraining and in-domain
#: evaluation", so pretraining is not disjoint from the benchmark. What is *not*
#: established is the row-level split — whether any particular electricity series
#: is pretraining-only or held out. Writing `yes` would assert something not
#: retrieved; writing `no` would be false. `undeclared` keeps the risk visibly
#: open, which is the only honest state for it.
WEIGHTS = {
    "repo": DEFAULT_REPO,
    "revision": "772f3d25d38aec6d914c8949dab4462e2d46f5d8",
    "sha256": "06a6a19bbe74bc10a9cd193bd4bf2bf638ae07f7e0d51653ae7ab8ea968a21dd",
    "bytes": 190_888_824,
    "license": "apache-2.0",
    "gated": False,
    "pretraining_corpus_declared": (
        'The model card states only "trained on nearly 100 billion time series '
        'observations" and enumerates no dataset. It also claims the 27 benchmark '
        'datasets were held out: "despite having no prior exposure to these '
        'datasets during training". Neither statement identifies the corpus.'
    ),
    "energy_domain_in_corpus": "undeclared",
    "energy_domain_evidence": (
        "arXiv:2403.07815 organises its dataset appendix by domain with a named "
        "B.1 Energy subsection, and Table 1 records Benchmark I (15 datasets, "
        "97,272 series) as 'pretraining and in-domain evaluation' — so pretraining "
        "is not disjoint from the benchmark. The row-level usage split for the "
        "individual electricity datasets was not retrieved, so this stays "
        "undeclared rather than yes."
    ),
    "verified_utc": "2026-08-06",
}

#: The values `energy_domain_in_corpus` may take. `undeclared` is a legitimate
#: answer and the most common honest one; what is forbidden is leaving the field
#: out, which is how the risk stops being visible.
ENERGY_DOMAIN_VALUES = ("yes", "no", "undeclared")
#: Context floor. `features.build.MIN_HISTORY_HOURS` is 672 hours measured from
#: the *target*; from the *origin* the GBM's deepest lag reaches 671 hours. Handing
#: the foundation model less than the GBM sees is how a comparison is rigged
#: without anyone deciding to rig it.
MIN_CONTEXT_HOURS = 671


def torch_is_loaded() -> bool:
    """Whether torch has been imported into this process. Used by the G5 test."""
    return "torch" in sys.modules


@dataclass
class ChronosArm:
    """A `predict_fn` for `models.backtest.run`, backed by a Chronos-Bolt pipeline.

    Univariate by construction, and that is not a limitation of this class — it
    is what the seam delivers. `predict_fn` receives `history: pd.Series` and
    nothing else; the GBM only sees twenty-seven features because it carries the
    panel inside itself.
    """

    repo: str = DEFAULT_REPO
    revision: str | None = None
    context_hours: int = MIN_CONTEXT_HOURS
    device: str = "cpu"
    quantile: float = 0.5

    #: `Any` rather than the real class, deliberately: annotating it would mean
    #: importing `chronos` at module scope, which is exactly what this file must
    #: not do. mypy runs with `ignore_missing_imports = true`, so it would have
    #: reported `Success` on a wrong annotation anyway — the import discipline is
    #: held by a test, not by the type checker.
    _pipeline: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.context_hours < MIN_CONTEXT_HOURS:
            raise ValueError(
                f"context_hours={self.context_hours} is below the {MIN_CONTEXT_HOURS}h "
                "the GBM's deepest lag reaches; a shorter window makes the comparison "
                "a statement about truncation rather than about the model."
            )

    def load(self) -> None:
        """Import torch and fetch the checkpoint. Never called during CI."""
        from chronos import BaseChronosPipeline  # lazy on purpose: see the module docstring

        self._pipeline = BaseChronosPipeline.from_pretrained(
            self.repo, revision=self.revision, device_map=self.device
        )

    def __call__(
        self, history: pd.Series, target_times: pd.DatetimeIndex, cutoff: pd.Timestamp
    ) -> pd.Series:
        if self._pipeline is None:
            raise RuntimeError("Call load() first; the checkpoint is not fetched at import.")
        if len(history.index) and history.index.max() >= cutoff:
            raise RuntimeError(
                f"history ends at {history.index.max()}, not strictly before {cutoff}"
            )

        import torch  # lazy on purpose: see the module docstring

        context = torch.tensor(
            history.to_numpy(dtype="float64")[-self.context_hours :], dtype=torch.float32
        )
        # `median_q50` is pre-registered: MAE is the judged metric and the median
        # is the L1-optimal functional. The GBM is trained with `objective: "l1"`,
        # so this is the only reduction that pairs with it.
        #
        # The batch goes in **positionally**, and that is not a style choice. The
        # first argument is named `context` in chronos-forecasting 1.x and
        # `inputs` in 2.x; this file was written against the 1.x name while
        # `uv.lock` resolves 2.3.1, so `context=` landed in `**kwargs` and the
        # call died with "missing 1 required positional argument: 'inputs'" —
        # measured, on the first line of this adapter ever to run with torch
        # installed. Positionally the same call is correct under both, and the
        # declared floor (`chronos-forecasting>=1.5`) stays honest.
        quantiles, _mean = self._pipeline.predict_quantiles(
            context.unsqueeze(0),
            prediction_length=len(target_times),
            quantile_levels=[self.quantile],
        )
        values = np.asarray(quantiles[0, :, 0], dtype="float64")
        return pd.Series(values, index=target_times, name="prediction")


def make_arm_factory(**kwargs):
    """Factory of factories for `foundation.guards.foresight_probe`.

    The probe rebuilds the arm from whatever series it hands over. A Chronos arm
    holds no series — it reads only the `history` slice the harness passes — so
    rebuilding is cheap and the probe stays honest.
    """

    def make_arm(_series: pd.Series) -> ChronosArm:
        arm = ChronosArm(**kwargs)
        arm.load()
        return arm

    return make_arm

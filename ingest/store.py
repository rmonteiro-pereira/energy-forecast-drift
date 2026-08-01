"""Partitioned parquet lake with idempotent, incremental appends.

Layout (all under `data/`, which is gitignored):

    data/raw/<dataset>/year=<YYYY>/month=<MM>/data.parquet

Idempotency contract
--------------------
`write_incremental` merges new rows into the partitions they belong to and
de-duplicates on the dataset's key columns, keeping the *newest* row. So:

  * re-running ingestion for a window already stored changes nothing;
  * a value revised upstream (the EIA revises recent hours) overwrites the
    stale one instead of creating a second row for the same timestamp.

Each partition file is written to a temporary path and then atomically moved
into place, so an interrupted run can never leave a half-written parquet.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ingest.config import Dataset

log = logging.getLogger(__name__)


@dataclass
class WriteReport:
    """What actually changed on disk during one `write_incremental` call."""

    dataset: str
    rows_received: int
    rows_added: int
    rows_updated: int
    rows_total: int
    partitions_touched: int

    def describe(self) -> str:
        return (
            f"{self.dataset}: received {self.rows_received} row(s) -> "
            f"+{self.rows_added} new, ~{self.rows_updated} revised, "
            f"{self.rows_total} total across {self.partitions_touched} partition(s)"
        )


def _partition_dir(dataset: Dataset, year: int, month: int) -> Path:
    return dataset.path / f"year={year:04d}" / f"month={month:02d}"


def _partition_file(dataset: Dataset, year: int, month: int) -> Path:
    return _partition_dir(dataset, year, month) / "data.parquet"


def _normalise_time(df: pd.DataFrame, dataset: Dataset) -> pd.DataFrame:
    df = df.copy()
    ts = pd.to_datetime(df[dataset.time_column], utc=True)
    df[dataset.time_column] = ts
    return df


def write_incremental(dataset: Dataset, df: pd.DataFrame) -> WriteReport:
    """Merge `df` into `dataset`, de-duplicating on the dataset key columns."""
    if df.empty:
        return WriteReport(dataset.name, 0, 0, 0, count_rows(dataset), 0)

    df = _normalise_time(df, dataset)
    # Guard against a source that hands us the same hour twice in one payload.
    df = df.drop_duplicates(subset=list(dataset.key_columns), keep="last")

    ts = df[dataset.time_column]
    df = df.assign(_year=ts.dt.year, _month=ts.dt.month)

    rows_added = rows_updated = partitions = 0

    for (year, month), chunk in df.groupby(["_year", "_month"], sort=True):
        chunk = chunk.drop(columns=["_year", "_month"])
        target = _partition_file(dataset, int(year), int(month))

        if target.exists():
            existing = pd.read_parquet(target)
            existing = _normalise_time(existing, dataset)
            keys = list(dataset.key_columns)
            known = set(map(tuple, existing[keys].itertuples(index=False, name=None)))
            incoming = set(map(tuple, chunk[keys].itertuples(index=False, name=None)))
            rows_added += len(incoming - known)
            rows_updated += len(incoming & known)
            # `keep="last"` => the freshly pulled row wins over the stored one.
            merged = pd.concat([existing, chunk], ignore_index=True)
            merged = merged.drop_duplicates(subset=keys, keep="last")
        else:
            rows_added += len(chunk)
            merged = chunk

        merged = merged.sort_values(list(dataset.key_columns)).reset_index(drop=True)
        _atomic_write(merged, target)
        partitions += 1

    report = WriteReport(
        dataset=dataset.name,
        rows_received=len(df),
        rows_added=rows_added,
        rows_updated=rows_updated,
        rows_total=count_rows(dataset),
        partitions_touched=partitions,
    )
    log.info(report.describe())
    return report


def _atomic_write(df: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, engine="pyarrow", index=False, compression="snappy")
    shutil.move(str(tmp), str(target))


def partition_files(dataset: Dataset) -> list[Path]:
    if not dataset.path.exists():
        return []
    return sorted(dataset.path.glob("year=*/month=*/data.parquet"))


def read_dataset(dataset: Dataset, columns: list[str] | None = None) -> pd.DataFrame:
    """Read the whole dataset, sorted by key. Empty frame when nothing stored."""
    files = partition_files(dataset)
    if not files:
        return pd.DataFrame()

    frames = [pd.read_parquet(f, columns=columns) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df = _normalise_time(df, dataset)
    sort_keys = [c for c in dataset.key_columns if c in df.columns]
    return df.sort_values(sort_keys).reset_index(drop=True)


def count_rows(dataset: Dataset) -> int:
    total = 0
    for f in partition_files(dataset):
        total += len(pd.read_parquet(f, columns=[dataset.time_column]))
    return total


def last_timestamp(
    dataset: Dataset, where: tuple[str, object] | None = None
) -> pd.Timestamp | None:
    """Newest stored timestamp, used to compute the incremental delta window.

    Only the most recent partition is opened, so this stays cheap as the lake
    grows.

    `where` narrows to one value of one column — `("site", "chicago_il")`. It
    exists because a multi-site dataset has one delta window *per site*: asking
    the dataset as a whole would report Philadelphia's newest hour and a city
    added later would never backfill. Absent from the newest partition means
    `None`, which the callers read as "pull the whole history" — the right
    answer for a site that is not there yet, and merely redundant for one that
    is behind.
    """
    files = partition_files(dataset)
    if not files:
        return None
    columns = [dataset.time_column] if where is None else [dataset.time_column, where[0]]
    newest = pd.read_parquet(files[-1], columns=columns)
    if where is not None:
        newest = newest[newest[where[0]] == where[1]]
    if newest.empty:
        return None
    return pd.to_datetime(newest[dataset.time_column], utc=True).max()

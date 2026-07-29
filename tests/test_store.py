"""The store's contract: incremental appends that never duplicate a timestamp."""

from __future__ import annotations

import pandas as pd
import pytest

from ingest import config, store
from ingest.config import Dataset


@pytest.fixture
def dataset(tmp_path, monkeypatch) -> Dataset:
    # Dataset.path resolves DATA_DIR at call time, so redirecting the lake root
    # is enough to sandbox every write into tmp_path.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return Dataset(
        name="demo",
        key_columns=("site", "timestamp_utc"),
        time_column="timestamp_utc",
    )


def frame(start: str, hours: int, value: float = 1.0, site: str = "a") -> pd.DataFrame:
    idx = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    return pd.DataFrame({"site": site, "timestamp_utc": idx, "value": value})


def test_first_write_stores_everything(dataset):
    report = store.write_incremental(dataset, frame("2026-01-01", 48))
    assert report.rows_added == 48
    assert report.rows_total == 48


def test_rewriting_the_same_window_is_a_no_op(dataset):
    store.write_incremental(dataset, frame("2026-01-01", 48))
    report = store.write_incremental(dataset, frame("2026-01-01", 48))

    assert report.rows_added == 0
    assert report.rows_updated == 48
    assert report.rows_total == 48, "re-ingesting must not duplicate timestamps"


def test_overlapping_delta_appends_only_the_new_hours(dataset):
    store.write_incremental(dataset, frame("2026-01-01", 48))
    report = store.write_incremental(dataset, frame("2026-01-02", 48))

    assert report.rows_added == 24
    assert report.rows_total == 72


def test_revised_values_overwrite_rather_than_accumulate(dataset):
    store.write_incremental(dataset, frame("2026-01-01", 24, value=100.0))
    store.write_incremental(dataset, frame("2026-01-01", 24, value=200.0))

    stored = store.read_dataset(dataset)
    assert len(stored) == 24
    assert (stored["value"] == 200.0).all(), "the newest pull must win"


def test_writes_are_partitioned_by_month(dataset):
    store.write_incremental(dataset, frame("2026-01-30", 24 * 5))
    partitions = {
        p.parent.parent.name + "/" + p.parent.name for p in store.partition_files(dataset)
    }
    assert partitions == {"year=2026/month=01", "year=2026/month=02"}


def test_distinct_keys_coexist_in_one_partition(dataset):
    store.write_incremental(dataset, frame("2026-01-01", 24, site="a"))
    report = store.write_incremental(dataset, frame("2026-01-01", 24, site="b"))

    assert report.rows_added == 24
    assert report.rows_total == 48


def test_last_timestamp_drives_the_delta_window(dataset):
    assert store.last_timestamp(dataset) is None
    store.write_incremental(dataset, frame("2026-01-01", 48))
    assert store.last_timestamp(dataset) == pd.Timestamp("2026-01-02 23:00", tz="UTC")


def test_empty_payload_leaves_the_lake_untouched(dataset):
    store.write_incremental(dataset, frame("2026-01-01", 24))
    report = store.write_incremental(dataset, pd.DataFrame())
    assert report.rows_total == 24

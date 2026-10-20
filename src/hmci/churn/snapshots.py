"""Build the churn base table: one row per (snapshot, active customer) with RFM, label and split."""
from __future__ import annotations

import math
from datetime import date, timedelta

import duckdb
import polars as pl

from hmci.common.config import Config, load_config


def snapshot_dates(cfg: Config) -> list[date]:
    d = cfg.raw["data"]
    start, end = date.fromisoformat(d["start_date"]), date.fromisoformat(d["end_date"])
    lookback = timedelta(weeks=d["active_lookback_weeks"])
    horizon = timedelta(weeks=d["churn_window_weeks"])
    step = timedelta(weeks=d["snapshot_step_weeks"])

    first = start + lookback                      # full feature history available
    last = end + timedelta(days=1) - horizon      # full label window fits in the data
    dates, s = [], first
    while s <= last:
        dates.append(s)
        s += step
    return dates


def assign_splits(dates: list[date], horizon_weeks: int, step_weeks: int) -> dict[date, str]:
    """Purged split: label windows of one split never reach into the next split."""
    gap = math.ceil(horizon_weeks / step_weeks)
    test_i = len(dates) - 1
    val_i = test_i - gap
    if val_i - gap < 0:
        raise ValueError("not enough snapshots for purged train/val/test splits")

    splits = {}
    for i, d in enumerate(dates):
        if i == test_i:
            splits[d] = "test"
        elif i == val_i:
            splits[d] = "val"
        elif i <= val_i - gap:
            splits[d] = "train"
        else:
            splits[d] = "gap"
    return splits


def build_base(cfg: Config) -> pl.DataFrame:
    d = cfg.raw["data"]
    dates = snapshot_dates(cfg)
    splits = assign_splits(dates, d["churn_window_weeks"], d["snapshot_step_weeks"])
    lookback_days = d["active_lookback_weeks"] * 7
    horizon_days = d["churn_window_weeks"] * 7

    frames = []
    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        for s in dates:
            df = con.execute(
                f"SELECT * FROM churn_labels(DATE '{s}', {lookback_days}, {horizon_days})"
            ).pl()
            frames.append(df.with_columns(split=pl.lit(splits[s])))
    return pl.concat(frames)


def main() -> None:
    cfg = load_config()
    base = build_base(cfg)
    out = cfg.paths.processed / "churn_base.parquet"
    base.write_parquet(out, compression="zstd")

    summary = (
        base.group_by("snapshot", "split")
        .agg(customers=pl.len(), churn_rate=pl.col("churned").mean().round(3))
        .sort("snapshot")
    )
    pl.Config.set_tbl_rows(30)
    print(summary)
    print(f"{base.height:,} rows -> {out.name}")


if __name__ == "__main__":
    main()
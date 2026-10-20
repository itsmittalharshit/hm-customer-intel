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


PROFILE_COLS = "c.age, c.age_band, c.fn, c.active, c.club_member_status, c.fashion_news_frequency"


def build_base(cfg: Config) -> pl.DataFrame:
    d = cfg.raw["data"]
    dates = snapshot_dates(cfg)
    splits = assign_splits(dates, d["churn_window_weeks"], d["snapshot_step_weeks"])
    lookback_days = d["active_lookback_weeks"] * 7
    horizon_days = d["churn_window_weeks"] * 7

    frames = []
    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        for s in dates:
            df = con.execute(f"""
                SELECT l.snapshot, l.customer_key, l.churned,
                       l.frequency_days AS check_freq,
                       f.* EXCLUDE (customer_key),
                       {PROFILE_COLS}
                FROM churn_labels(DATE '{s}', {lookback_days}, {horizon_days}) l
                JOIN churn_features(DATE '{s}', {lookback_days}) f USING (customer_key)
                JOIN dim_customer c USING (customer_key)
            """).pl()
            print(f"{s}  {df.height:>9,} rows")
            frames.append(df.with_columns(split=pl.lit(splits[s])))

    base = pl.concat(frames)
    # the label population and the feature population must be the same customers
    assert (base["check_freq"] == base["freq_26w"]).all(), "labels and features disagree"
    return base.drop("check_freq")


def main() -> None:
    cfg = load_config()
    base = build_base(cfg)
    out = cfg.paths.processed / "churn_features.parquet"
    base.write_parquet(out, compression="zstd")

    pl.Config.set_tbl_rows(40)
    pl.Config.set_tbl_cols(12)
    train = base.filter(pl.col("split") == "train")
    print(train.group_by("churned").agg(
        pl.col("recency_days", "freq_26w", "spend_26w", "gap_trend", "online_share", "tenure_days").mean()
    ).sort("churned"))
    print(base.null_count().transpose(include_header=True, column_names=["nulls"]).filter(pl.col("nulls") > 0))
    print(f"{base.height:,} rows x {base.width} columns -> {out.name}")

if __name__ == "__main__":
    main()
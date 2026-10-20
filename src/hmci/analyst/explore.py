"""Analyst layer, part 1: cohort retention, first-channel mix, channel segments, RFM segments."""
from __future__ import annotations

from datetime import date

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from hmci.common.config import load_config

FIRST_CLEAN_COHORT = date(2019, 3, 1)
MAX_MONTHS = 17


def overall_retention(ret: pl.DataFrame) -> pl.DataFrame:
    """Sum counts across channels, then divide (never average ratios)."""
    return (
        ret.group_by("cohort_month", "months_since_first", "left_censored", "partial_month")
        .agg(pl.col("active_customers").sum(), pl.col("cohort_size").sum())
        .with_columns(retention=pl.col("active_customers") / pl.col("cohort_size"))
        .sort("cohort_month", "months_since_first")
    )


def main() -> None:
    cfg = load_config()
    out_dir = cfg.paths.reports / "analyst"
    fig_dir = cfg.paths.reports / "figures"
    out_dir.mkdir(exist_ok=True)

    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        ret = con.execute("SELECT * FROM v_cohort_retention").pl()
        first_channel = con.execute("""
            SELECT cohort_month, count(*) AS new_customers,
                   avg((first_channel = 2)::INTEGER) AS first_online_share
            FROM v_customer_cohort GROUP BY ALL ORDER BY 1
        """).pl()
        mix = con.execute("""
            SELECT channel_mix, count(*) AS customers,
                   avg(purchase_days) AS avg_purchase_days,
                   avg(spend) AS avg_spend, median(spend) AS median_spend
            FROM v_customer_channel_mix GROUP BY ALL ORDER BY customers DESC
        """).pl()
        mix_band = con.execute("""
            SELECT CASE WHEN purchase_days = 1  THEN '1'
                        WHEN purchase_days <= 3 THEN '2-3'
                        WHEN purchase_days <= 10 THEN '4-10'
                        ELSE '11+' END AS purchase_days_band,
                   channel_mix, count(*) AS customers, avg(spend) AS avg_spend
            FROM v_customer_channel_mix GROUP BY ALL ORDER BY 1, 2
        """).pl()
        segments = con.execute("""
            SELECT segment, count(*) AS customers,
                   avg(recency_days) AS avg_recency, avg(frequency_days) AS avg_frequency,
                   sum(monetary) AS revenue
            FROM v_rfm_segments GROUP BY ALL
        """).pl()

    # ---------- checks ----------
    overall = overall_retention(ret)
    m0 = overall.filter(pl.col("months_since_first") == 0)["retention"]
    assert (m0 == 1.0).all(), "month-0 retention must be exactly 100%"

    # ---------- 1. cohort retention ----------
    clean = overall.filter(
        (pl.col("cohort_month") >= FIRST_CLEAN_COHORT) & ~pl.col("partial_month")
        & (pl.col("months_since_first") <= MAX_MONTHS)
    )
    key_months = (
        clean.filter(pl.col("months_since_first").is_in([1, 3, 6, 12]))
        .pivot(on="months_since_first", index="cohort_month", values="retention")
        .rename({"1": "m1", "3": "m3", "6": "m6", "12": "m12"})
        .sort("cohort_month")
        .with_columns(pl.exclude("cohort_month").round(3))
    )
    pl.Config.set_tbl_rows(30)
    print("Retention by cohort (share of the cohort buying again in month k):")
    print(key_months)

    heat = clean.pivot(on="months_since_first", index="cohort_month", values="retention").sort("cohort_month")
    month_cols = sorted([c for c in heat.columns if c != "cohort_month"], key=int)
    values = heat.select(month_cols).to_numpy().astype(float)
    values[:, 0] = np.nan                     # month 0 is always 100%: hide it so colours show real variation
    fig, ax = plt.subplots(figsize=(12, 7))
    im = ax.imshow(values, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(month_cols)), month_cols)
    ax.set_yticks(range(heat.height), [d.strftime("%Y-%m") for d in heat["cohort_month"]])
    for i in range(values.shape[0]):
        for j in range(1, values.shape[1]):
            if not np.isnan(values[i, j]):
                ax.text(j, i, f"{values[i, j]:.0%}", ha="center", va="center", fontsize=6,
                        color="white" if values[i, j] > np.nanmax(values) * 0.6 else "black")
    ax.set(xlabel="months since first purchase", ylabel="cohort (first-purchase month)",
           title="Monthly cohort retention (cohorts from 2019-03; partial Sep 2020 excluded)")
    fig.colorbar(im, ax=ax, format=matplotlib.ticker.PercentFormatter(1.0))
    fig.tight_layout()
    fig.savefig(fig_dir / "cohort_retention_heatmap.png", dpi=150)

    # ---------- 2. first channel: the April 2020 hypothesis ----------
    print("\nNew customers and share whose FIRST purchase was channel 2 (online):")
    print(first_channel.filter(pl.col("cohort_month") >= FIRST_CLEAN_COHORT)
          .with_columns(pl.col("first_online_share").round(3)))

    by_channel = (
        ret.filter((pl.col("cohort_month") >= FIRST_CLEAN_COHORT) & ~pl.col("partial_month")
                   & pl.col("months_since_first").is_between(1, 6))
        .group_by("first_channel", "months_since_first")
        .agg((pl.col("active_customers").sum() / pl.col("cohort_size").sum()).round(3).alias("retention"))
        .pivot(on="months_since_first", index="first_channel", values="retention")
        .sort("first_channel")
        .select("first_channel", *[str(m) for m in range(1, 7)])
    )
    print("\nRetention months 1-6 by first-purchase channel (1 = store, 2 = online):")
    print(by_channel)

    # ---------- 3. channel mix (beware: frequency confounds it) ----------
    print("\nChannel mix over full history:")
    print(mix.with_columns(share=(pl.col("customers") / pl.col("customers").sum()).round(3),
                           avg_purchase_days=pl.col("avg_purchase_days").round(2),
                           avg_spend=pl.col("avg_spend").round(4), median_spend=pl.col("median_spend").round(4)))
    print("\nSame comparison WITHIN purchase-frequency bands (fairer):")
    band_order = {"1": 0, "2-3": 1, "4-10": 2, "11+": 3}
    print(mix_band.pivot(on="channel_mix", index="purchase_days_band", values="avg_spend")
          .sort(pl.col("purchase_days_band").replace_strict(band_order))
          .with_columns(pl.exclude("purchase_days_band").round(4)))

    # ---------- 4. RFM segments ----------
    seg = segments.with_columns(
        share_customers=(pl.col("customers") / pl.col("customers").sum()).round(3),
        share_revenue=(pl.col("revenue") / pl.col("revenue").sum()).round(3),
        avg_recency=pl.col("avg_recency").round(1), avg_frequency=pl.col("avg_frequency").round(2),
    ).drop("revenue").sort("share_revenue", descending=True)
    print("\nRFM segments (last 52 weeks, as of 2020-09-23):")
    print(seg)

    # ---------- exports for Tableau ----------
    ret.write_csv(out_dir / "cohort_retention_counts.csv")
    first_channel.write_csv(out_dir / "cohort_first_channel.csv")
    mix.write_csv(out_dir / "channel_mix.csv")
    mix_band.write_csv(out_dir / "channel_mix_by_frequency.csv")
    seg.write_csv(out_dir / "rfm_segments.csv")
    print(f"\nexported 5 CSVs to {out_dir}")


if __name__ == "__main__":
    main()
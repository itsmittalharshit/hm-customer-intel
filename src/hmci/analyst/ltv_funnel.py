"""Analyst layer, part 2: 12-month lifetime value curves and the repeat-purchase funnel."""
from __future__ import annotations

from datetime import date

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from hmci.common.config import load_config

LTV_COHORTS = (date(2019, 3, 1), date(2019, 9, 1))   # clean AND 12 complete months observed
FUNNEL_FIRST = (date(2019, 3, 1), date(2019, 9, 22))  # full 365-day window after first purchase
STEPS = {"1st purchase": 1, "2nd purchase": 2, "3rd purchase": 3, "5+ purchases (loyal)": 5}
CHANNEL = {1: "store-first", 2: "online-first"}


def ltv_curves(rev: pl.DataFrame, sizes: pl.DataFrame) -> pl.DataFrame:
    """Average cumulative spend per customer, months 0-11, by first channel."""
    in_window = pl.col("cohort_month").is_between(*LTV_COHORTS)
    totals = sizes.filter(in_window).group_by("first_channel").agg(pl.col("cohort_size").sum())
    return (
        rev.filter(in_window & (pl.col("months_since_first") < 12))
        .group_by("first_channel", "months_since_first").agg(pl.col("revenue").sum())
        .join(totals, on="first_channel")
        .sort("first_channel", "months_since_first")
        .with_columns(cum_ltv=pl.col("revenue").cum_sum().over("first_channel") / pl.col("cohort_size"))
    )


def ltv_by_cohort(rev: pl.DataFrame, sizes: pl.DataFrame, last_complete: date) -> pl.DataFrame:
    """6- and 12-month LTV per cohort; null when the window is not fully observed."""
    size = sizes.group_by("cohort_month").agg(pl.col("cohort_size").sum())
    agg = (
        rev.group_by("cohort_month").agg(
            ltv_6m=pl.col("revenue").filter(pl.col("months_since_first") < 6).sum(),
            ltv_12m=pl.col("revenue").filter(pl.col("months_since_first") < 12).sum(),
        )
        .join(size, on="cohort_month")
        .with_columns(pl.col("ltv_6m", "ltv_12m") / pl.col("cohort_size"))
    )
    months_seen = (last_complete.year - pl.col("cohort_month").dt.year()) * 12 \
        + (last_complete.month - pl.col("cohort_month").dt.month()) + 1
    return (
        agg.with_columns(
            pl.when(months_seen >= 6).then("ltv_6m").alias("ltv_6m"),
            pl.when(months_seen >= 12).then("ltv_12m").alias("ltv_12m"),
        )
        .filter(pl.col("cohort_month") >= LTV_COHORTS[0])
        .sort("cohort_month")
    )


def funnel(journey: pl.DataFrame) -> pl.DataFrame:
    counts = [int((journey["visits_365d"] >= k).sum()) for k in STEPS.values()]
    return pl.DataFrame({"step": list(STEPS), "customers": counts}).with_columns(
        share_of_new=(pl.col("customers") / counts[0]).round(3),
        step_conversion=(pl.col("customers") / pl.col("customers").shift(1)).round(3),
    )


def days_between(journey: pl.DataFrame, start: str, end: str) -> float:
    d = journey.filter(pl.col(end) < pl.col("first_purchase") + pl.duration(days=365))
    return float((d[end] - d[start]).dt.total_days().median())


def main() -> None:
    cfg = load_config()
    out_dir = cfg.paths.reports / "analyst"
    fig_dir = cfg.paths.reports / "figures"

    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        rev = con.execute("SELECT * FROM v_cohort_revenue").pl()
        sizes = con.execute("SELECT cohort_month, first_channel, count(*) AS cohort_size "
                            "FROM v_customer_cohort GROUP BY ALL").pl()
        journey = con.execute(f"""
            SELECT * FROM v_customer_journey
            WHERE first_purchase BETWEEN DATE '{FUNNEL_FIRST[0]}' AND DATE '{FUNNEL_FIRST[1]}'
        """).pl()

    # ---------- 1. LTV ----------
    curves = ltv_curves(rev, sizes)
    curve_table = curves.pivot(on="first_channel", index="months_since_first", values="cum_ltv") \
        .rename({"1": "store-first", "2": "online-first"}).with_columns(pl.exclude("months_since_first").round(4))
    pl.Config.set_tbl_rows(30)
    print("Average cumulative spend per new customer (cohorts 2019-03 to 2019-09):")
    print(curve_table)

    by_cohort = ltv_by_cohort(rev, sizes, last_complete=date(2020, 8, 1))
    print("\n6- and 12-month LTV per new customer, by cohort:")
    print(by_cohort.with_columns(pl.col("ltv_6m", "ltv_12m").round(4)))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for ch, name in CHANNEL.items():
        c = curves.filter(pl.col("first_channel") == ch)
        ax.plot(c["months_since_first"], c["cum_ltv"], marker="o", label=name)
    ax.set(xlabel="months since first purchase", ylabel="cumulative spend per customer (scaled)",
           title="12-month value of a new customer, by first channel")
    ax.legend()
    fig.tight_layout()
    fig.savefig(fig_dir / "ltv_curves_by_channel.png", dpi=150)

    # ---------- 2. funnel ----------
    print(f"\nRepeat-purchase funnel, first 365 days ({journey.height:,} customers, first purchase "
          f"{FUNNEL_FIRST[0]} to {FUNNEL_FIRST[1]}):")
    overall = funnel(journey)
    print(overall)
    print(f"median days 1st -> 2nd purchase: {days_between(journey, 'first_purchase', 'second_purchase'):.0f}")
    print(f"median days 2nd -> 3rd purchase: {days_between(journey, 'second_purchase', 'third_purchase'):.0f}")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(overall["step"].to_list()[::-1], overall["share_of_new"].to_list()[::-1])
    for i, v in enumerate(overall["share_of_new"].to_list()[::-1]):
        ax.text(v + 0.01, i, f"{v:.0%}", va="center")
    ax.set(xlim=(0, 1.1), xlabel="share of new customers reaching the step within 365 days",
           title="Repeat-purchase funnel")
    fig.tight_layout()
    fig.savefig(fig_dir / "repeat_purchase_funnel.png", dpi=150)

    def repeat_stats(group_col: str) -> pl.DataFrame:
        return (
            journey.group_by(group_col).agg(
                customers=pl.len(),
                repeat_12m=(pl.col("visits_365d") >= 2).mean().round(3),
                loyal_12m=(pl.col("visits_365d") >= 5).mean().round(3),
            ).sort("customers", descending=True)
        )

    by_channel = repeat_stats("first_channel").with_columns(
        pl.col("first_channel").replace_strict(CHANNEL, return_dtype=pl.Utf8))
    print("\nBy first channel:")
    print(by_channel)

    by_group = repeat_stats("first_group").head(10).sort("repeat_12m", descending=True)
    print("\nBy first-purchase product group (10 largest entry groups):")
    print(by_group)

    # ---------- exports for Tableau ----------
    curves.write_csv(out_dir / "ltv_curves.csv")
    by_cohort.write_csv(out_dir / "ltv_by_cohort.csv")
    overall.write_csv(out_dir / "funnel_overall.csv")
    by_channel.write_csv(out_dir / "funnel_by_channel.csv")
    by_group.write_csv(out_dir / "funnel_by_entry_group.csv")
    print(f"\nexported 5 CSVs to {out_dir}")


if __name__ == "__main__":
    main()
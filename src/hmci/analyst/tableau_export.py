"""Write tidy, labelled CSVs for Tableau Public (one file per chart)."""
from __future__ import annotations

from datetime import date

import duckdb
import polars as pl

from hmci.analyst.ltv_funnel import CHANNEL, FUNNEL_FIRST, LTV_COHORTS, funnel, ltv_curves
from hmci.common.config import load_config

END_NEXT_DAY = date(2020, 9, 23)
CLEAN_COHORT = date(2019, 3, 1)


def label_channel(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("first_channel").replace_strict(CHANNEL, return_dtype=pl.Utf8))


def main() -> None:
    cfg = load_config()
    out = cfg.paths.reports / "tableau"
    out.mkdir(exist_ok=True)

    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        q = lambda sql: con.execute(sql).pl()
        ret = q("SELECT * FROM v_cohort_retention")
        rev = q("SELECT * FROM v_cohort_revenue")
        sizes = q("SELECT cohort_month, first_channel, count(*) AS cohort_size FROM v_customer_cohort GROUP BY ALL")
        journey = q(f"SELECT * FROM v_customer_journey WHERE first_purchase BETWEEN "
                    f"DATE '{FUNNEL_FIRST[0]}' AND DATE '{FUNNEL_FIRST[1]}'")
        segments = q("SELECT segment, count(*) AS customers, sum(monetary) AS revenue FROM v_rfm_segments GROUP BY ALL")
        active = q(f"SELECT count(*) AS n FROM rfm(DATE '{END_NEXT_DAY}', 182)")["n"][0]
        online_share = q(f"""
            SELECT sum(revenue) FILTER (WHERE channel_key = 2) / sum(revenue) AS s
            FROM fact_sales WHERE date_key >= DATE '{END_NEXT_DAY}' - 364""")["s"][0]

    # 1. cohort retention (counts; Tableau computes SUM(active)/SUM(size))
    label_channel(ret.filter((pl.col("cohort_month") >= CLEAN_COHORT) & ~pl.col("partial_month")
                             & pl.col("months_since_first").is_between(1, 17))) \
        .select("cohort_month", "first_channel", "months_since_first", "active_customers", "cohort_size") \
        .write_csv(out / "cohort_retention.csv")

    # 2. LTV curves
    curves = label_channel(ltv_curves(rev, sizes))
    curves.select("first_channel", "months_since_first", "cum_ltv").write_csv(out / "ltv_curves.csv")

    # 3. funnel: overall and by first channel, long format
    parts = [funnel(journey).with_columns(segment=pl.lit("all new customers"))]
    for ch, name in CHANNEL.items():
        parts.append(funnel(journey.filter(pl.col("first_channel") == ch)).with_columns(segment=pl.lit(name)))
    funnel_long = pl.concat(parts).with_columns(step_order=pl.int_range(pl.len()).over("segment") + 1)
    funnel_long.write_csv(out / "funnel.csv")

    # 4. RFM segments: customer share vs revenue share, long format
    seg = segments.with_columns(
        customers_share=pl.col("customers") / pl.col("customers").sum(),
        revenue_share=pl.col("revenue") / pl.col("revenue").sum(),
    ).unpivot(index="segment", on=["customers_share", "revenue_share"], variable_name="measure", value_name="share")
    seg.write_csv(out / "rfm_segments.csv")

    # 5. hypothesis tests: short labels for the chart
    tests = pl.read_csv(cfg.paths.reports / "analyst" / "hypothesis_tests.csv").with_columns(
        finding=pl.Series([
            "Store-first repeat more (+7.6pp)", "Club ACTIVE vs PRE-CREATE (+27pp)",
            "Newsletter subscribers repeat more (+12pp)", "Online-first spend more (mean)",
            "Entry product group", "Lockdown cohort vs March 2020",
        ])
    ).select("finding", "effect_size", "effect_measure", "diff", "ci95_low", "ci95_high", "p_adj_bh", "significant")
    tests.write_csv(out / "hypothesis_tests.csv")

    # 6. KPI tiles
    last = curves.filter(pl.col("months_since_first") == 11)
    ltv_all = (last["cum_ltv"] * last["cohort_size"]).sum() / last["cohort_size"].sum()
    f = funnel(journey)
    champions = seg.filter((pl.col("segment") == "Champions") & (pl.col("measure") == "revenue_share"))["share"][0]
    pl.DataFrame({
        "kpi": ["Active customers (last 26 weeks)", "New customers who buy again within 12 months",
                "12-month value of a new customer (scaled)", "Online share of revenue (last 52 weeks)",
                "Revenue from Champions (22% of customers)"],
        "value": [float(active), f["share_of_new"][1], float(ltv_all), float(online_share), float(champions)],
        "format": ["number", "percent", "decimal", "percent", "percent"],
    }).write_csv(out / "kpis.csv")

    for p in sorted(out.glob("*.csv")):
        print(f"{p.name:24s} {sum(1 for _ in open(p)) - 1:>6,} rows")


if __name__ == "__main__":
    main()
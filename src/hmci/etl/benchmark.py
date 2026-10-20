"""Time 3 benchmark queries on DuckDB (native and on Parquet) and Polars; write reports/benchmarks.md."""
from __future__ import annotations

import statistics
import time
from datetime import date

import duckdb
import polars as pl

from hmci.common.config import load_config

SNAPSHOT = date(2020, 6, 1)
LOOKBACK_DAYS = 182
TOP_FROM = date(2020, 8, 26)          # last 4 weeks of data (to 2020-09-22)
REPEATS = 5


def duckdb_queries(src: str, articles: str) -> dict[str, str]:
    """src/articles are table names or read_parquet(...) calls, so one SQL text serves both modes."""
    return {
        "weekly revenue by department": f"""
            SELECT date_trunc('week', f.date_key) AS week, a.department_name, sum(f.revenue) AS revenue
            FROM {src} f JOIN {articles} a USING (article_key) GROUP BY ALL""",
        "top-100 articles, last 4 weeks": f"""
            SELECT article_key, sum(units) AS units FROM {src}
            WHERE date_key >= DATE '{TOP_FROM}' GROUP BY article_key ORDER BY units DESC LIMIT 100""",
        "customer RFM at snapshot": f"""
            SELECT customer_key,
                   date_diff('day', max(date_key), DATE '{SNAPSHOT}') AS recency_days,
                   count(DISTINCT date_key) AS frequency_days,
                   sum(revenue) AS monetary, sum(units)::BIGINT AS units
            FROM {src}
            WHERE date_key < DATE '{SNAPSHOT}' AND date_key >= DATE '{SNAPSHOT}' - {LOOKBACK_DAYS}
            GROUP BY customer_key""",
    }


def polars_queries(processed) -> dict[str, pl.LazyFrame]:
    tx = pl.scan_parquet(processed / "transactions.parquet").with_columns(
        revenue=pl.col("price").cast(pl.Float64) * pl.col("units")
    )
    art = pl.scan_parquet(processed / "articles.parquet").select("article_key", "department_name")
    start = SNAPSHOT.fromordinal(SNAPSHOT.toordinal() - LOOKBACK_DAYS)
    return {
        "weekly revenue by department": (
            tx.join(art, on="article_key")
            .group_by(pl.col("t_dat").dt.truncate("1w").alias("week"), "department_name")
            .agg(pl.col("revenue").sum())
        ),
        "top-100 articles, last 4 weeks": (
            tx.filter(pl.col("t_dat") >= TOP_FROM)
            .group_by("article_key").agg(pl.col("units").sum())
            .top_k(100, by="units")
        ),
        "customer RFM at snapshot": (
            tx.filter((pl.col("t_dat") < SNAPSHOT) & (pl.col("t_dat") >= start))
            .group_by("customer_key")
            .agg(
                recency_days=(pl.lit(SNAPSHOT) - pl.col("t_dat").max()).dt.total_days(),
                frequency_days=pl.col("t_dat").n_unique(),
                monetary=pl.col("revenue").sum(),
                units=pl.col("units").sum(),
            )
        ),
    }


def time_it(fn) -> tuple[float, int]:
    """Run once to warm up, then REPEATS times; return median seconds and result row count."""
    rows = fn()
    runs = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs), rows


def main() -> None:
    cfg = load_config()
    p = cfg.paths.processed
    fact_pq = f"read_parquet('{p}/transactions.parquet')"
    art_pq = f"read_parquet('{p}/articles.parquet')"

    # Parquet column is t_dat; the native table calls it date_key -> alias in a subquery
    fact_pq_aliased = f"(SELECT t_dat AS date_key, article_key, customer_key, units, price::DOUBLE * units AS revenue FROM {fact_pq})"

    results = []  # (query, engine, seconds, rows)
    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        for engine, src, arts in [
            ("DuckDB (native tables)", "fact_sales", "dim_article"),
            ("DuckDB (on Parquet)", fact_pq_aliased, art_pq),
        ]:
            for name, sql in duckdb_queries(src, arts).items():
                secs, rows = time_it(lambda: len(con.execute(sql).fetchall()))
                results.append((name, engine, secs, rows))

    for name, lf in polars_queries(p).items():
        secs, rows = time_it(lambda: lf.collect().height)
        results.append((name, "Polars (lazy, Parquet)", secs, rows))

    # every engine must return the same number of rows per query
    for name in {r[0] for r in results}:
        counts = {r[3] for r in results if r[0] == name}
        assert len(counts) == 1, f"engines disagree on '{name}': {counts}"

    lines = ["# Benchmarks", "",
             f"MacBook Air M4, median of {REPEATS} runs after one warm-up, 28.8M fact rows.", "",
             "| Query | Engine | Median (s) | Rows |", "| --- | --- | --- | --- |"]
    for name, engine, secs, rows in sorted(results):
        lines.append(f"| {name} | {engine} | {secs:.3f} | {rows:,} |")
    out = cfg.paths.reports / "benchmarks.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
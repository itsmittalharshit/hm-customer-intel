"""Build warehouse.duckdb from the Parquet lake, then run data-quality checks."""
from __future__ import annotations

import time

import duckdb

from hmci.common.config import ROOT, load_config
from hmci.etl.build_parquet import EXPECTED_RAW_ROWS

SQL_DIR = ROOT / "sql"
SQL_FILES = ["schema.sql", "macros.sql", "views.sql", "churn.sql",
             "analyst/cohorts.sql", "analyst/segments.sql", "analyst/ltv_funnel.sql"]

EXPECTED_FACT_ROWS = 28_813_419

# name -> (query returning one number, expected value)
CHECKS = {
    "fact rows":               ("SELECT count(*) FROM fact_sales", EXPECTED_FACT_ROWS),
    "units add up to raw rows": ("SELECT sum(units) FROM fact_sales", EXPECTED_RAW_ROWS),
    "orphan customers":        ("SELECT count(*) FROM fact_sales ANTI JOIN dim_customer USING (customer_key)", 0),
    "orphan articles":         ("SELECT count(*) FROM fact_sales ANTI JOIN dim_article USING (article_key)", 0),
    "orphan channels":         ("SELECT count(*) FROM fact_sales ANTI JOIN dim_channel USING (channel_key)", 0),
    "orphan dates":            ("SELECT count(*) FROM fact_sales ANTI JOIN dim_date USING (date_key)", 0),
    "duplicate customer keys": ("SELECT count(*) - count(DISTINCT customer_key) FROM dim_customer", 0),
    "duplicate article keys":  ("SELECT count(*) - count(DISTINCT article_key) FROM dim_article", 0),
    "non-positive revenue":    ("SELECT count(*) FROM fact_sales WHERE revenue <= 0", 0),
}


def build(con: duckdb.DuckDBPyConnection, processed: str) -> None:
    for name in SQL_FILES:
        sql = (SQL_DIR / name).read_text().replace("{processed}", processed)
        con.execute(sql)
        print(f"ran   {name}")


def run_checks(con: duckdb.DuckDBPyConnection) -> None:
    failed = []
    for name, (query, expected) in CHECKS.items():
        value = con.execute(query).fetchone()[0]
        status = "ok  " if value == expected else "FAIL"
        print(f"{status}  {name}: {value:,} (expected {expected:,})")
        if value != expected:
            failed.append(name)
    if failed:
        raise SystemExit(f"data-quality checks failed: {failed}")


def main() -> None:
    cfg = load_config()
    cfg.paths.make_dirs()
    t0 = time.perf_counter()
    # full rebuild: start from an empty file so freed space doesn't accumulate
    cfg.paths.warehouse.unlink(missing_ok=True)
    cfg.paths.warehouse.with_suffix(".duckdb.wal").unlink(missing_ok=True)
    with duckdb.connect(str(cfg.paths.warehouse)) as con:
        build(con, str(cfg.paths.processed))
        run_checks(con)
        print(con.execute("SELECT * FROM rfm(DATE '2020-06-01', 182) LIMIT 3").pl())
    size_mb = cfg.paths.warehouse.stat().st_size / 1e6
    print(f"warehouse {size_mb:.0f} MB, built in {time.perf_counter() - t0:.0f}s")

if __name__ == "__main__":
    main()
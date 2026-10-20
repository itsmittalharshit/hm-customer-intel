from datetime import date

import duckdb

from hmci.common.config import ROOT


def test_rfm_excludes_snapshot_day_and_after():
    con = duckdb.connect()  # in-memory database
    con.execute("""
        CREATE TABLE fact_sales AS SELECT * FROM (VALUES
            (DATE '2020-01-01', 1, 10.0, 1),
            (DATE '2020-01-20', 1, 20.0, 2),
            (DATE '2020-02-01', 1, 99.0, 9),   -- ON the snapshot day: must be excluded
            (DATE '2020-03-01', 2, 50.0, 1)    -- after the snapshot: must be excluded
        ) AS t(date_key, customer_key, revenue, units)
    """)
    con.execute((ROOT / "sql" / "macros.sql").read_text())

    rows = con.execute("SELECT * FROM rfm(DATE '2020-02-01', 182)").fetchall()

    assert rows == [(1, 12, 2, 30.0, 3)]  # recency 12 days, 2 purchase days, spend 30, units 3
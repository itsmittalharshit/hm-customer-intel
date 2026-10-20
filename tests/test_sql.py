from datetime import date

import duckdb

from hmci.common.config import ROOT

def test_churn_labels():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE fact_sales AS SELECT * FROM (VALUES
            (DATE '2020-01-10', 1, 10.0, 1),
            (DATE '2020-02-15', 1, 10.0, 1),   -- buys again inside the window -> stays
            (DATE '2020-01-15', 2, 10.0, 1),   -- no purchase after snapshot -> churns
            (DATE '2020-02-10', 3, 10.0, 1)    -- first purchase after snapshot -> not in population
        ) AS t(date_key, customer_key, revenue, units)
    """)
    con.execute((ROOT / "sql" / "macros.sql").read_text())

    rows = con.execute(
        "SELECT customer_key, churned FROM churn_labels(DATE '2020-02-01', 182, 126) ORDER BY 1"
    ).fetchall()

    assert rows == [(1, 0), (2, 1)]
    
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

def test_churn_features_ignore_snapshot_day():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE dim_article AS SELECT * FROM (VALUES (1, 'A'), (2, 'B')) AS t(article_key, product_group_name);
        CREATE TABLE fact_sales AS SELECT * FROM (VALUES
            (DATE '2020-01-01', 1, 1, 2, 1.0, 1, 1.0),
            (DATE '2020-01-21', 1, 2, 1, 2.0, 1, 2.0),
            (DATE '2020-02-01', 1, 1, 2, 99.0, 9, 891.0)   -- snapshot day: must be ignored
        ) AS t(date_key, customer_key, article_key, channel_key, price, units, revenue);
    """)
    con.execute((ROOT / "sql" / "churn.sql").read_text())

    row = con.execute("""
        SELECT recency_days, freq_26w, freq_4w, spend_26w, online_share,
               n_product_groups, gap_mean, tenure_days
        FROM churn_features(DATE '2020-02-01', 182)
    """).fetchone()

    # recency 11 (Feb 1 - Jan 21); 2 visits; 1 visit in last 4 weeks; spend 3.0;
    # half the units online; 2 product groups; one 20-day gap; tenure 31 days
    assert row == (11, 2, 1, 3.0, 0.5, 2, 20.0, 31)
"""Generate docs/data_dictionary.md from the live warehouse schema."""
from __future__ import annotations

import duckdb

from hmci.common.config import ROOT, load_config

DESCRIPTIONS = {
    "fact_sales": "One row per (day, customer, article, price, channel); identical raw rows collapsed into units.",
    "dim_customer": "One row per customer, including 9,699 who never purchased.",
    "dim_article": "One row per article, including 995 never sold.",
    "dim_date": "One row per calendar day, 2018-09-20 to 2020-09-22.",
    "dim_channel": "Two sales channels; meaning inferred, not documented.",
    "v_weekly_category_demand": "Weekly units, revenue and buyers per garment group; days_observed < 7 = partial week.",
    "v_customer_cohort": "First purchase date, cohort month and first channel per customer; cohorts before 2019-03 are left-censored.",
    "date_key": "Calendar date (DATE); the key of dim_date.",
    "customer_key": "int32 surrogate key, assigned by sorting the original customer_id.",
    "article_key": "int32 surrogate key, assigned by sorting the original 10-digit article_id.",
    "channel_key": "1 or 2; 2 is likely online.",
    "price": "Scaled price per unit (not real currency).",
    "units": "Number of identical raw rows collapsed into this row.",
    "revenue": "price * units, in scaled units.",
    "fn": "1 if subscribed to fashion news, else 0 (nulls treated as 0).",
    "active": "1 if the customer is flagged active for communication, else 0 (nulls treated as 0).",
    "age_band": "Age grouped into bands; 'unknown' when age is missing.",
    "covid_lockdown": "True between 2020-03-15 and 2020-05-31 (approximate).",
    "days_observed": "Distinct days with sales in that week; 7 = full week.",
}


def main() -> None:
    cfg = load_config()
    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        cols = con.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """).fetchall()
        tables = [r[0] for r in con.execute("SELECT DISTINCT table_name FROM information_schema.columns "
                                             "WHERE table_schema = 'main' ORDER BY 1").fetchall()]
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}

    lines = ["# Data dictionary", "", "Generated from `warehouse.duckdb` by `make docs`. Do not edit by hand.", ""]
    for t in tables:
        lines += [f"## `{t}` ({counts[t]:,} rows)", "", DESCRIPTIONS.get(t, ""), "",
                  "| Column | Type | Description |", "| --- | --- | --- |"]
        for table, col, dtype in cols:
            if table == t:
                lines.append(f"| `{col}` | {dtype} | {DESCRIPTIONS.get(col, '')} |")
        lines.append("")

    out = ROOT / "docs" / "data_dictionary.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"wrote {out} ({len(tables)} tables and views)")


if __name__ == "__main__":
    main()
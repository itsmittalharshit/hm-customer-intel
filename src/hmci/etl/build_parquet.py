"""Raw CSV -> typed Parquet with int32 surrogate keys and a units column."""
from __future__ import annotations

import time
from pathlib import Path

import polars as pl

from hmci.common.config import load_config

EXPECTED_RAW_ROWS = 31_788_324  # from the EDA notebook

TX_SCHEMA = {
    "customer_id": pl.Utf8,
    "article_id": pl.Utf8,
    "price": pl.Float32,
    "sales_channel_id": pl.Int8,
}

ARTICLE_COLS = [
    "article_id", "product_code", "prod_name", "product_type_name", "product_group_name",
    "graphical_appearance_name", "colour_group_name", "perceived_colour_master_name",
    "department_name", "index_name", "index_group_name", "section_name",
    "garment_group_name", "detail_desc",
]


def build_customers(raw_dir: Path) -> pl.DataFrame:
    df = pl.read_csv(raw_dir / "customers.csv", schema_overrides={"postal_code": pl.Utf8})
    return (
        df.sort("customer_id")                       # sorted -> keys are reproducible
        .with_row_index("customer_key")
        .with_columns(
            pl.col("customer_key").cast(pl.Int32),
            pl.col("FN").fill_null(0).cast(pl.Int8).alias("fn"),
            pl.col("Active").fill_null(0).cast(pl.Int8).alias("active"),
            pl.col("club_member_status").fill_null("UNKNOWN"),
            pl.col("fashion_news_frequency").str.to_uppercase().fill_null("NONE"),
            pl.col("age").cast(pl.Int16),
        )
        .select("customer_key", "customer_id", "fn", "active", "club_member_status",
                "fashion_news_frequency", "age", "postal_code")
    )


def build_articles(raw_dir: Path) -> pl.DataFrame:
    df = pl.read_csv(raw_dir / "articles.csv", schema_overrides={"article_id": pl.Utf8})
    return (
        df.sort("article_id")
        .with_row_index("article_key")
        .with_columns(pl.col("article_key").cast(pl.Int32))
        .select(["article_key", *ARTICLE_COLS])
    )


def build_transactions(raw_dir: Path, customers: pl.DataFrame, articles: pl.DataFrame) -> pl.DataFrame:
    cust_map = customers.select("customer_id", "customer_key").lazy()
    art_map = articles.select("article_id", "article_key").lazy()
    return (
        pl.scan_csv(raw_dir / "transactions_train.csv", schema_overrides=TX_SCHEMA, try_parse_dates=True)
        .join(cust_map, on="customer_id", how="left")   # left: unknown IDs become nulls we can detect
        .join(art_map, on="article_id", how="left")
        .group_by(["t_dat", "customer_key", "article_key", "price", "sales_channel_id"])
        .agg(pl.len().cast(pl.Int16).alias("units"))   # identical rows -> one row with units
        .sort(["t_dat", "customer_key"])
        .collect(engine="streaming")
    )


def check(tx: pl.DataFrame, customers: pl.DataFrame, articles: pl.DataFrame) -> None:
    assert tx["customer_key"].null_count() == 0, "transactions with an unknown customer_id"
    assert tx["article_key"].null_count() == 0, "transactions with an unknown article_id"
    assert tx["units"].cast(pl.Int64).sum() == EXPECTED_RAW_ROWS, "units do not add up to raw rows"
    assert (tx["price"] > 0).all(), "non-positive price"
    assert customers["customer_id"].n_unique() == customers.height, "duplicate customer_id"
    assert articles["article_id"].n_unique() == articles.height, "duplicate article_id"


def main() -> None:
    cfg = load_config()
    cfg.paths.make_dirs()
    raw, out = cfg.paths.raw, cfg.paths.processed

    t0 = time.perf_counter()
    customers = build_customers(raw)
    articles = build_articles(raw)
    tx = build_transactions(raw, customers, articles)
    check(tx, customers, articles)

    customers.write_parquet(out / "customers.parquet", compression="zstd")
    articles.write_parquet(out / "articles.parquet", compression="zstd")
    tx.write_parquet(out / "transactions.parquet", compression="zstd",
                     row_group_size=1_000_000, statistics=True)

    print(f"customers {customers.height:,} | articles {articles.height:,} | transactions {tx.height:,}")
    for f in sorted(out.glob("*.parquet")):
        print(f"{f.name:22s} {f.stat().st_size / 1e6:8.1f} MB")
    print(f"done in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
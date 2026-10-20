import polars as pl

from hmci.etl.build_parquet import build_transactions


def test_duplicates_collapse_to_units(tmp_path):
    pl.DataFrame({
        "t_dat": ["2020-01-01"] * 3,
        "customer_id": ["a", "a", "b"],
        "article_id": ["0100000001"] * 3,
        "price": [0.05, 0.05, 0.05],
        "sales_channel_id": [2, 2, 1],
    }).write_csv(tmp_path / "transactions_train.csv")

    customers = pl.DataFrame({"customer_id": ["a", "b"], "customer_key": [0, 1]},
                             schema_overrides={"customer_key": pl.Int32})
    articles = pl.DataFrame({"article_id": ["0100000001"], "article_key": [0]},
                            schema_overrides={"article_key": pl.Int32})

    tx = build_transactions(tmp_path, customers, articles)

    assert tx.height == 2                         # a's two identical rows became one
    assert sorted(tx["units"].to_list()) == [1, 2]
    assert tx["article_key"].to_list() == [0, 0]  # leading-zero ID still matched
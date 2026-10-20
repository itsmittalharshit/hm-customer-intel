"""LightGBM churn model: early stopping on a customer hold-out from train, small grid scored on val."""
from __future__ import annotations

import time

import joblib
import lightgbm as lgb
import pandas as pd
import polars as pl
import polars.selectors as cs

from hmci.churn.baselines import LIN_COLS, LOG_COLS, TARGET
from hmci.churn.metrics import evaluate, write_markdown
from hmci.common.config import ROOT, Config, load_config

NUM_COLS = LOG_COLS + LIN_COLS + ["age"]          # trees need no log or scaling; raw age is fine
CAT_COLS = ["club_member_status", "fashion_news_frequency"]
FEATURES = NUM_COLS + CAT_COLS

BASE_PARAMS = dict(
    objective="binary",
    metric="average_precision",   # early stopping watches PR-AUC
    learning_rate=0.05,
    n_estimators=3000,            # upper bound; early stopping picks the real number
    subsample=0.8, subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    n_jobs=-1,
    verbose=-1,
)
GRID = [
    {"num_leaves": 31,  "min_child_samples": 200},
    {"num_leaves": 63,  "min_child_samples": 200},
    {"num_leaves": 127, "min_child_samples": 500},
    {"num_leaves": 255, "min_child_samples": 1000},
]


def load_split(cfg: Config, split: str) -> pd.DataFrame:
    return (
        pl.scan_parquet(cfg.paths.processed / "churn_features.parquet")
        .filter(pl.col("split") == split)
        .select("customer_key", *FEATURES, TARGET)
        .collect()
        .to_pandas()
    )


def set_categories(train: pd.DataFrame, others: list[pd.DataFrame]) -> None:
    """Categories are learned from train and imposed on the other splits, so codes always match."""
    for c in CAT_COLS:
        train[c] = train[c].astype("category")
        for df in others:
            df[c] = pd.Categorical(df[c], categories=train[c].cat.categories)


def main() -> None:
    cfg = load_config()
    train, val = load_split(cfg, "train"), load_split(cfg, "val")
    set_categories(train, [val])

    # early-stopping set: 10% of CUSTOMERS from train, so no customer is on both sides
    es_mask = train["customer_key"] % 10 == 0
    fit, es = train[~es_mask], train[es_mask]
    print(f"fit {len(fit):,} | early-stop {len(es):,} | val {len(val):,}")

    runs, best = [], None
    for params in GRID:
        t0 = time.perf_counter()
        model = lgb.LGBMClassifier(**BASE_PARAMS, **params)
        model.fit(fit[FEATURES], fit[TARGET], eval_X=es[FEATURES], eval_y=es[TARGET],
            callbacks=[lgb.early_stopping(100, verbose=False)])
        p_va = model.predict_proba(val[FEATURES])[:, 1]   # uses the best iteration automatically
        row = evaluate(f"lgbm leaves={params['num_leaves']} mcs={params['min_child_samples']}",
                       val[TARGET].to_numpy(), p_va)
        row |= {"trees": model.best_iteration_, "fit_s": round(time.perf_counter() - t0)}
        runs.append(row)
        print(row)
        if best is None or row["pr_auc"] > best[1]["pr_auc"]:
            best = (model, row)

    model, best_row = best
    p_tr = model.predict_proba(train[FEATURES])[:, 1]
    summary = pl.DataFrame([
        evaluate("lgbm best (train)", train[TARGET].to_numpy(), p_tr),
        {k: v for k, v in best_row.items() if k not in ("trees", "fit_s")} | {"model": "lgbm best (val)"},
    ]).with_columns(cs.numeric().round(4))

    pl.Config.set_tbl_cols(10)
    grid_table = pl.DataFrame(runs).with_columns(cs.numeric().round(4))
    print(grid_table)
    print(summary)

    importance = (
        pl.DataFrame({"feature": FEATURES,
                      "gain": model.booster_.feature_importance(importance_type="gain")})
        .with_columns((pl.col("gain") / pl.col("gain").sum()).round(3).alias("share"))
        .sort("gain", descending=True)
        .select("feature", "share")
    )
    pl.Config.set_tbl_rows(30)
    print(importance)

    joblib.dump(model, ROOT / "models" / "churn_lgbm.joblib")
    write_markdown(grid_table, cfg.paths.reports / "churn_lgbm.md", "LightGBM grid (validation snapshot)")


if __name__ == "__main__":
    main()
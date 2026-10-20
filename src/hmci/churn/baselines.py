"""Churn baselines: constant, recency rule, logistic regression. Scored on the validation snapshot."""
from __future__ import annotations
from hmci.churn.metrics import evaluate, write_markdown
import time

import joblib
import numpy as np
import polars as pl
import polars.selectors as cs
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from hmci.common.config import ROOT, Config, load_config

# skewed counts and amounts: log1p before scaling
LOG_COLS = ["recency_days", "freq_4w", "freq_12w", "freq_26w", "spend_4w", "spend_12w", "spend_26w",
            "units_26w", "basket_value", "tenure_days", "gap_mean", "gap_last"]
# already on a sensible scale (shares, small counts, flags, a signed difference)
LIN_COLS = ["gap_trend", "online_share", "n_product_groups", "below_median_share", "fn", "active"]
CAT_COLS = ["age_band", "club_member_status", "fashion_news_frequency"]
FEATURES = LOG_COLS + LIN_COLS + CAT_COLS
TARGET = "churned"


def load_split(cfg: Config, split: str):
    return (
        pl.scan_parquet(cfg.paths.processed / "churn_features.parquet")
        .filter(pl.col("split") == split)
        .select(*FEATURES, TARGET)
        .collect()
        .to_pandas()
    )


def make_logreg() -> Pipeline:
    log_pipe = Pipeline([
        ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),  # adds "was missing" columns
        ("scale", StandardScaler()),
    ])
    lin_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value=0)),      # no gap -> no trend
        ("scale", StandardScaler()),
    ])
    pre = ColumnTransformer([
        ("log", log_pipe, LOG_COLS),
        ("lin", lin_pipe, LIN_COLS),
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=0.01), CAT_COLS),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(C=1.0, max_iter=1000))])



def main() -> None:
    cfg = load_config()
    train, val = load_split(cfg, "train"), load_split(cfg, "val")
    y_tr, y_va = train[TARGET].to_numpy(), val[TARGET].to_numpy()
    print(f"train {len(train):,} rows (churn {y_tr.mean():.3f}) | val {len(val):,} rows (churn {y_va.mean():.3f})")

    results = [
        evaluate("constant (train churn rate)", y_va, np.full(len(y_va), y_tr.mean())),
        evaluate("rule: recency_days", y_va, val["recency_days"].to_numpy(), is_prob=False),
    ]

    t0 = time.perf_counter()
    model = make_logreg().fit(train[FEATURES], y_tr)
    print(f"logistic regression fitted in {time.perf_counter() - t0:.0f}s")

    results.append(evaluate("logistic regression (train)", y_tr, model.predict_proba(train[FEATURES])[:, 1]))
    results.append(evaluate("logistic regression", y_va, model.predict_proba(val[FEATURES])[:, 1]))

    table = pl.DataFrame(results).with_columns(cs.numeric().round(4))
    pl.Config.set_tbl_cols(8)
    print(table)

    names = model.named_steps["pre"].get_feature_names_out()
    coefs = (
        pl.DataFrame({"feature": names, "coef": model.named_steps["clf"].coef_[0]})
        .with_columns(pl.col("coef").round(3))
        .sort(pl.col("coef").abs(), descending=True)
    )
    pl.Config.set_tbl_rows(40)
    print(coefs)

    (ROOT / "models").mkdir(exist_ok=True)
    joblib.dump(model, ROOT / "models" / "churn_logreg.joblib")
    write_markdown(table, cfg.paths.reports / "churn_baselines.md", "Churn baselines (validation snapshot)")


if __name__ == "__main__":
    main()
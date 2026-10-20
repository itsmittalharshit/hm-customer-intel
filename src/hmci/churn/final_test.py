"""Score the untouched TEST snapshot ONCE with the frozen models, calibrators and targeting policy."""
from __future__ import annotations

import sys

import joblib
import numpy as np
import polars as pl
import polars.selectors as cs

from hmci.churn import baselines, lgbm
from hmci.churn.evaluate import MODELS, N_BOOT, apply_calibrator, ece, load_val, paired_bootstrap
from hmci.churn.metrics import evaluate, write_markdown
from hmci.churn.targeting import summarise, top_k_mask
from hmci.common.config import ROOT, load_config

FEATURES = {"logreg": baselines.FEATURES, "lgbm": lgbm.FEATURES}


def main() -> None:
    cfg = load_config()
    out_metrics = cfg.paths.reports / "churn_test_metrics.md"
    if out_metrics.exists() and "--force" not in sys.argv:
        raise SystemExit("Test snapshot already scored. Re-running invites tuning on test; use --force only "
                         "if the pipeline changed for reasons unrelated to test results.")

    df = load_val(cfg, split="test")
    y = df["churned"].to_numpy()
    train_rate = (pl.scan_parquet(cfg.paths.processed / "churn_features.parquet")
                  .filter(pl.col("split") == "train").select(pl.col("churned").mean()).collect().item())
    print(f"test snapshot: {len(df):,} customers, churn rate {y.mean():.3f}")

    # ---------- 1. metrics: baselines, raw and calibrated models ----------
    rows = [
        evaluate("constant (train churn rate)", y, np.full(len(y), train_rate)),
        evaluate("rule: recency_days", y, df["recency_days"].to_numpy(), is_prob=False),
    ]
    calibrators = joblib.load(ROOT / "models" / "churn_calibrators.joblib")
    probs = {}
    for name, file in MODELS.items():
        raw = joblib.load(ROOT / "models" / file).predict_proba(df[FEATURES[name]])[:, 1]
        method, cal = calibrators[name]
        p = apply_calibrator(method, cal, raw)
        probs[name] = (raw, p)
        for label, q in [("raw", raw), (f"calibrated ({method})", p)]:
            rows.append(evaluate(f"{name} {label}", y, q)
                        | {"ece": ece(y, q), "mean_pred": float(q.mean()), "observed": float(y.mean())})
    metrics = pl.from_dicts(rows, infer_schema_length=None).with_columns(cs.numeric().round(4))
    pl.Config.set_tbl_cols(10)
    print(metrics)

    # ---------- 2. paired bootstrap on test ----------
    boot = paired_bootstrap(y, probs["logreg"][0], probs["lgbm"][0], N_BOOT, cfg.seed)
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
    est = [float(np.mean(boot[:, i])) for i in range(3)]
    ci = pl.DataFrame({"quantity": ["PR-AUC logreg", "PR-AUC lgbm", "lgbm - logreg"],
                       "bootstrap_mean": est, "ci95_low": lo, "ci95_high": hi}).with_columns(cs.numeric().round(4))
    print(ci)
    print(f"share of resamples where lgbm <= logreg: {(boot[:, 2] <= 0).mean():.3f}")

    # ---------- 3. targeting policy on test, same assumptions as validation ----------
    biz, d = cfg.raw["churn_business"], cfg.raw["data"]
    s = biz["save_rate"]
    p = probs["lgbm"][1]
    spend = df["spend_26w"].to_numpy()
    v = spend * d["churn_window_weeks"] / d["active_lookback_weeks"]
    cost = biz["offer_cost_share"] * spend.mean()
    ev_mask = p * s * v - cost > 0
    k = int(ev_mask.sum())
    policies = pl.DataFrame([
        summarise("EV > 0 (value-aware)", ev_mask, p, y, v, s, cost),
        summarise("same k, ranked by churn prob", top_k_mask(p, k), p, y, v, s, cost),
        summarise("top 10% by churn prob", top_k_mask(p, int(0.10 * len(p))), p, y, v, s, cost),
        summarise("target everyone", np.ones(len(p), dtype=bool), p, y, v, s, cost),
    ]).with_columns(cs.float().round(3))
    print(policies)

    write_markdown(metrics, out_metrics, "Churn: test snapshot 2020-05-14 (scored once)")
    write_markdown(ci, cfg.paths.reports / "churn_test_bootstrap.md", "Paired bootstrap on test (200 resamples)")
    write_markdown(policies, cfg.paths.reports / "churn_test_targeting.md",
                   f"Targeting on test (simulation: save rate {s:.0%}, offer cost {biz['offer_cost_share']:.0%} of mean spend)")


if __name__ == "__main__":
    main()
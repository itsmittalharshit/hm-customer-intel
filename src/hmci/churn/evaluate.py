"""Validation snapshot: paired bootstrap LogReg vs LightGBM, then calibration (Platt vs isotonic)."""
from __future__ import annotations

import joblib
import matplotlib

matplotlib.use("Agg")  # write figures to files, no window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import polars.selectors as cs
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss

from hmci.churn import baselines, lgbm
from hmci.churn.metrics import write_markdown
from hmci.common.config import ROOT, Config, load_config

N_BOOT = 200
MODELS = {"logreg": "churn_logreg.joblib", "lgbm": "churn_lgbm.joblib"}


def load_val(cfg: Config) -> pd.DataFrame:
    cols = sorted(set(baselines.FEATURES) | set(lgbm.FEATURES) | {"customer_key", "churned"})
    df = (pl.scan_parquet(cfg.paths.processed / "churn_features.parquet")
          .filter(pl.col("split") == "val").select(cols).collect().to_pandas())
    for c in lgbm.CAT_COLS:
        df[c] = df[c].astype("category")   # LightGBM re-maps to its training categories
    return df


def predict_all(df: pd.DataFrame) -> dict[str, np.ndarray]:
    features = {"logreg": baselines.FEATURES, "lgbm": lgbm.FEATURES}
    return {name: joblib.load(ROOT / "models" / f).predict_proba(df[features[name]])[:, 1]
            for name, f in MODELS.items()}


def paired_bootstrap(y, p_a, p_b, n_boot: int, seed: int) -> np.ndarray:
    """Each resample scores BOTH models on the SAME rows -> columns: AP(a), AP(b), AP(b) - AP(a)."""
    rng = np.random.default_rng(seed)
    n = len(y)
    out = np.empty((n_boot, 3))
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        a = average_precision_score(y[idx], p_a[idx])
        b = average_precision_score(y[idx], p_b[idx])
        out[i] = (a, b, b - a)
    return out


# ---------- calibration ----------
def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_calibrator(method: str, p, y):
    if method == "platt":
        return LogisticRegression().fit(logit(p).reshape(-1, 1), y)
    return IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(p, y)


def apply_calibrator(method: str, cal, p):
    if method == "uncalibrated":
        return p
    if method == "platt":
        return cal.predict_proba(logit(p).reshape(-1, 1))[:, 1]
    return cal.predict(p)


def ece(y, p, bins: int = 10) -> float:
    """Expected calibration error: gap between predicted and observed churn, averaged over score bins."""
    idx = np.clip((p * bins).astype(int), 0, bins - 1)
    return float(sum((idx == b).mean() * abs(p[idx == b].mean() - y[idx == b].mean())
                     for b in range(bins) if (idx == b).any()))


def main() -> None:
    cfg = load_config()
    df = load_val(cfg)
    y = df["churned"].to_numpy()
    preds = predict_all(df)

    # ---------- 1. paired bootstrap ----------
    boot = paired_bootstrap(y, preds["logreg"], preds["lgbm"], N_BOOT, cfg.seed)
    point = [average_precision_score(y, preds["logreg"]), average_precision_score(y, preds["lgbm"])]
    point.append(point[1] - point[0])
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
    ci = pl.DataFrame({
        "quantity": ["PR-AUC logreg", "PR-AUC lgbm", "lgbm - logreg"],
        "estimate": point, "ci95_low": lo, "ci95_high": hi,
    }).with_columns(cs.numeric().round(4))
    print(ci)
    print(f"share of resamples where lgbm <= logreg: {(boot[:, 2] <= 0).mean():.3f}")

    # ---------- 2. calibration: fit on half A, evaluate on half B (split by customer) ----------
    half_a = (df["customer_key"] % 2 == 0).to_numpy()
    rows, fig, axes = [], *plt.subplots(1, 2, figsize=(11, 4.5))
    calibrators = {}
    for ax, (name, p) in zip(axes, preds.items()):
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
        best = None
        for method in ["uncalibrated", "platt", "isotonic"]:
            cal = None if method == "uncalibrated" else fit_calibrator(method, p[half_a], y[half_a])
            p_b = apply_calibrator(method, cal, p[~half_a])
            yb = y[~half_a]
            row = {"model": name, "method": method, "log_loss": log_loss(yb, p_b),
                   "brier": brier_score_loss(yb, p_b), "ece": ece(yb, p_b),
                   "mean_pred": p_b.mean(), "observed": yb.mean()}
            rows.append(row)
            frac_pos, mean_pred = calibration_curve(yb, p_b, n_bins=10)
            ax.plot(mean_pred, frac_pos, marker="o", label=method)
            if method != "uncalibrated" and (best is None or row["log_loss"] < best[1]):
                best = (method, row["log_loss"])
        ax.set(title=f"{name}: reliability on val half B", xlabel="predicted churn probability",
               ylabel="observed churn rate")
        ax.legend()
        # refit the winning method on ALL of val for use on test later
        calibrators[name] = (best[0], fit_calibrator(best[0], p, y))

    fig_dir = cfg.paths.reports / "figures"
    fig_dir.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(fig_dir / "churn_reliability.png", dpi=150)

    cal_table = pl.DataFrame(rows).with_columns(cs.numeric().round(4))
    pl.Config.set_tbl_cols(8)
    print(cal_table)
    print({k: v[0] for k, v in calibrators.items()})

    joblib.dump(calibrators, ROOT / "models" / "churn_calibrators.joblib")
    write_markdown(ci, cfg.paths.reports / "churn_bootstrap.md", "Paired bootstrap on validation (200 resamples)")
    write_markdown(cal_table, cfg.paths.reports / "churn_calibration.md", "Calibration on validation half B")


if __name__ == "__main__":
    main()
"""SHAP explanations for the LightGBM churn model on a validation sample."""
from __future__ import annotations

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import shap

from hmci.churn import lgbm
from hmci.churn.evaluate import load_val
from hmci.common.config import ROOT, load_config

N_SAMPLE = 50_000
DEPENDENCE = ["recency_days", "freq_26w", "gap_trend"]


def main() -> None:
    cfg = load_config()
    fig_dir = cfg.paths.reports / "figures"
    df = load_val(cfg).sample(N_SAMPLE, random_state=cfg.seed).reset_index(drop=True)
    model = joblib.load(ROOT / "models" / "churn_lgbm.joblib")
    X = df[lgbm.FEATURES]

    # exact TreeSHAP: one column per feature + a final column holding the base value
    contrib = model.booster_.predict(X, pred_contrib=True)
    values, base = contrib[:, :-1], contrib[:, -1]
    raw = model.booster_.predict(X, raw_score=True)
    assert np.allclose(values.sum(axis=1) + base, raw, atol=1e-6), "SHAP values must add up to the prediction"
    p = model.predict_proba(X)[:, 1]

    # ---------- 1. global importance: mean |SHAP| vs gain ----------
    gain = model.booster_.feature_importance(importance_type="gain")
    imp = (
        pl.DataFrame({"feature": lgbm.FEATURES,
                      "mean_abs_shap": np.abs(values).mean(axis=0),
                      "gain_share": gain / gain.sum()})
        .with_columns(shap_share=pl.col("mean_abs_shap") / pl.col("mean_abs_shap").sum())
        .sort("mean_abs_shap", descending=True)
        .with_columns(pl.col("mean_abs_shap", "gain_share", "shap_share").round(3))
    )
    pl.Config.set_tbl_rows(30)
    print(imp)

    # ---------- 2. beeswarm: direction and spread for every feature ----------
    data = X.copy()
    for c in lgbm.CAT_COLS:
        data[c] = data[c].cat.codes          # colours need numbers; codes keep category order
    exp = shap.Explanation(values=values, base_values=base,
                           data=data.to_numpy(dtype=float), feature_names=lgbm.FEATURES)
    shap.plots.beeswarm(exp, max_display=15, show=False)
    plt.title("SHAP: what pushes churn risk up (right) or down (left)")
    plt.tight_layout()
    plt.savefig(fig_dir / "churn_shap_beeswarm.png", dpi=150)
    plt.close()

    # ---------- 3. dependence: how the effect changes with the feature value ----------
    fig, axes = plt.subplots(1, len(DEPENDENCE), figsize=(14, 4))
    for ax, f in zip(axes, DEPENDENCE):
        i = lgbm.FEATURES.index(f)
        ax.scatter(X[f], values[:, i], s=2, alpha=0.15)
        ax.axhline(0, color="black", lw=0.5)
        ax.set_xlim(right=np.nanpercentile(X[f], 99))
        ax.set(xlabel=f, ylabel="SHAP (log-odds of churn)", title=f)
    fig.tight_layout()
    fig.savefig(fig_dir / "churn_shap_dependence.png", dpi=150)

    club_i = lgbm.FEATURES.index("club_member_status")
    print(pl.DataFrame({"club_member_status": X["club_member_status"].astype(str),
                        "shap": values[:, club_i]})
          .group_by("club_member_status").agg(pl.len().alias("n"), pl.col("shap").mean().round(3))
          .sort("shap", descending=True))

    # ---------- 4. three individual explanations ----------
    picks = {"highest risk": int(np.argmax(p)), "borderline": int(np.argmin(np.abs(p - 0.5))),
             "lowest risk": int(np.argmin(p))}
    for name, i in picks.items():
        top = np.argsort(-np.abs(values[i]))[:5]
        print(f"\n{name}: customer {df.loc[i, 'customer_key']}  p(churn)={p[i]:.3f}  "
              f"actually churned={df.loc[i, 'churned']}  base log-odds={base[i]:.3f}")
        for j in top:
            f = lgbm.FEATURES[j]
            print(f"   {f:22s} = {str(X.iloc[i][f]):>10s}   SHAP {values[i, j]:+.3f}")

    # ---------- 5. save for the dashboard ----------
    out = pl.from_pandas(df[["customer_key", *lgbm.FEATURES, "churned"]].astype(
        {c: str for c in lgbm.CAT_COLS})).with_columns(pl.Series("p_churn_raw", p))
    shap_df = pl.DataFrame(values, schema=[f"shap_{f}" for f in lgbm.FEATURES])
    pl.concat([out, shap_df], how="horizontal").write_parquet(cfg.paths.reports / "churn_shap_sample.parquet")
    print(f"\nsaved {N_SAMPLE:,} explained customers for the dashboard")


if __name__ == "__main__":
    main()
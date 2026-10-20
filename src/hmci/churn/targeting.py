"""Cost-sensitive retention targeting on the validation snapshot (a simulation under stated assumptions)."""
from __future__ import annotations

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import polars.selectors as cs

from hmci.churn import lgbm
from hmci.churn.evaluate import apply_calibrator, load_val
from hmci.churn.metrics import write_markdown
from hmci.common.config import ROOT, load_config


def top_k_mask(score: np.ndarray, k: int) -> np.ndarray:
    mask = np.zeros(len(score), dtype=bool)
    mask[np.argsort(-score)[:k]] = True
    return mask


def summarise(name, mask, p, y, v, s, cost) -> dict:
    """Expected outcome uses predicted p; realised outcome uses the true labels y."""
    return {
        "policy": name,
        "targeted": int(mask.sum()),
        "share_targeted": mask.mean(),
        "expected_saved": float(p[mask].sum() * s),
        "realised_saved": float(y[mask].sum() * s),
        "offer_cost": float(cost * mask.sum()),
        "expected_net": float((p[mask] * s * v[mask]).sum() - cost * mask.sum()),
        "realised_net": float((y[mask] * s * v[mask]).sum() - cost * mask.sum()),
    }


def main() -> None:
    cfg = load_config()
    biz = cfg.raw["churn_business"]
    d = cfg.raw["data"]
    s = biz["save_rate"]

    df = load_val(cfg)
    y = df["churned"].to_numpy()
    model = joblib.load(ROOT / "models" / "churn_lgbm.joblib")
    method, cal = joblib.load(ROOT / "models" / "churn_calibrators.joblib")["lgbm"]
    p = apply_calibrator(method, cal, model.predict_proba(df[lgbm.FEATURES])[:, 1])

    spend = df["spend_26w"].to_numpy()
    v = spend * d["churn_window_weeks"] / d["active_lookback_weeks"]   # value if kept, over the label window
    cost = biz["offer_cost_share"] * spend.mean()
    ev = p * s * v - cost

    # ---------- policies ----------
    ev_mask = ev > 0
    k = int(ev_mask.sum())
    policies = pl.DataFrame([
        summarise("EV > 0 (value-aware)", ev_mask, p, y, v, s, cost),
        summarise("same k, ranked by churn prob", top_k_mask(p, k), p, y, v, s, cost),
        summarise("top 10% by churn prob", top_k_mask(p, int(0.10 * len(p))), p, y, v, s, cost),
        summarise("target everyone", np.ones(len(p), dtype=bool), p, y, v, s, cost),
    ]).with_columns(cs.float().round(3))
    pl.Config.set_tbl_cols(10)
    print(f"assumptions: save rate {s:.0%}, offer cost {cost:.4f} (= {biz['offer_cost_share']:.0%} of mean spend)")
    print(f"break-even churn probability for an average-value customer: {cost / (s * v.mean()):.3f}")
    print(policies)

    # ---------- profit curves (realised, using true labels) ----------
    gain = y * s * v - cost
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(1, len(y) + 1) / len(y)
    for label, score in [("ranked by expected value", ev), ("ranked by churn probability", p)]:
        curve = np.cumsum(gain[np.argsort(-score)])
        ax.plot(x[::200], curve[::200], label=f"{label} (max {curve.max():.1f})")
    ax.plot([0, 1], [0, gain.sum()], "k--", lw=1, label="random targeting")
    ax.axvline(ev_mask.mean(), color="grey", ls=":", label=f"EV > 0 policy ({ev_mask.mean():.0%})")
    ax.axhline(0, color="black", lw=0.5)
    ax.set(xlabel="share of customers targeted", ylabel="net value (scaled spend units)",
           title="Retention offer: net value vs how many we target (simulation)")
    ax.legend(fontsize=8)
    fig_dir = cfg.paths.reports / "figures"
    fig.tight_layout()
    fig.savefig(fig_dir / "churn_profit_curve.png", dpi=150)

    # ---------- sensitivity to the two assumptions ----------
    rows = []
    for sr in biz["save_rate_grid"]:
        for cs_ in biz["offer_cost_grid"]:
            c = cs_ * spend.mean()
            mask = p * sr * v > c
            rows.append({"save_rate": sr, "cost_share": cs_, "share_targeted": mask.mean(),
                         "realised_net": float((y[mask] * sr * v[mask]).sum() - c * mask.sum())})
    sens = pl.DataFrame(rows)
    grid = sens.pivot(on="cost_share", index="save_rate", values="realised_net")
    print(grid.with_columns(pl.exclude("save_rate").round(1)))

    fig, ax = plt.subplots(figsize=(6, 4.5))
    values = grid.drop("save_rate").to_numpy()
    im = ax.imshow(values, cmap="viridis", origin="lower")
    ax.set_xticks(range(len(biz["offer_cost_grid"])), [f"{c:.0%}" for c in biz["offer_cost_grid"]])
    ax.set_yticks(range(len(biz["save_rate_grid"])), [f"{r:.0%}" for r in biz["save_rate_grid"]])
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            share = sens.filter((pl.col("save_rate") == biz["save_rate_grid"][i]) &
                                (pl.col("cost_share") == biz["offer_cost_grid"][j]))["share_targeted"][0]
            ax.text(j, i, f"{values[i, j]:.0f}\n({share:.0%})", ha="center", va="center", color="white", fontsize=8)
    ax.set(xlabel="offer cost (share of mean spend)", ylabel="save rate",
           title="Net value (share targeted) under each assumption")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(fig_dir / "churn_sensitivity.png", dpi=150)

    write_markdown(policies, cfg.paths.reports / "churn_targeting.md",
                   f"Retention targeting on validation (simulation: save rate {s:.0%}, "
                   f"offer cost {biz['offer_cost_share']:.0%} of mean spend)")


if __name__ == "__main__":
    main()
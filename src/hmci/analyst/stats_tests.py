"""Analyst layer, part 3: hypothesis tests with BH correction, and A/B test design for the retention offer."""
from __future__ import annotations

from datetime import date
from math import asin, ceil, sqrt

import duckdb
import numpy as np
import polars as pl
from scipy.stats import chi2_contingency, mannwhitneyu
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from hmci.churn.metrics import write_markdown
from hmci.common.config import load_config

FUNNEL_FIRST = (date(2019, 3, 1), date(2019, 9, 22))   # every customer has a full 365-day window
MIN_GROUP = 1_000


def cohens_h(p1: float, p2: float) -> float:
    """Effect size for two proportions: ~0.2 small, ~0.5 medium, ~0.8 large."""
    return 2 * asin(sqrt(p1)) - 2 * asin(sqrt(p2))


def two_prop(test: str, a: np.ndarray, b: np.ndarray, label_a: str, label_b: str) -> dict:
    ka, na, kb, nb = int(a.sum()), len(a), int(b.sum()), len(b)
    _, p = proportions_ztest([ka, kb], [na, nb])
    lo, hi = confint_proportions_2indep(ka, na, kb, nb, method="wald", compare="diff")
    pa, pb = ka / na, kb / nb
    return {"test": test, "method": "two-proportion z-test",
            "group_a": f"{label_a} (n={na:,})", "group_b": f"{label_b} (n={nb:,})",
            "value_a": pa, "value_b": pb, "diff": pa - pb, "ci95_low": lo, "ci95_high": hi,
            "effect_size": cohens_h(pa, pb), "effect_measure": "Cohen's h", "p_value": p}


def mann_whitney(test: str, a: np.ndarray, b: np.ndarray, label_a: str, label_b: str) -> dict:
    u, p = mannwhitneyu(a, b, alternative="two-sided")
    diff = a.mean() - b.mean()
    se = sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return {"test": test, "method": "Mann-Whitney U (CI: Welch, mean diff)",
            "group_a": f"{label_a} (n={len(a):,})", "group_b": f"{label_b} (n={len(b):,})",
            "value_a": a.mean(), "value_b": b.mean(), "diff": diff,
            "ci95_low": diff - 1.96 * se, "ci95_high": diff + 1.96 * se,
            "effect_size": u / (len(a) * len(b)), "effect_measure": "P(A > B)", "p_value": p}


def chi_square(test: str, groups: pl.Series, outcome: np.ndarray) -> dict:
    g = (pl.DataFrame({"g": groups, "y": outcome})
         .group_by("g").agg(n=pl.len(), k=pl.col("y").sum())
         .filter(pl.col("n") >= MIN_GROUP)
         .with_columns(rate=pl.col("k") / pl.col("n"))
         .sort("rate"))
    table = np.column_stack([g["k"].to_numpy(), (g["n"] - g["k"]).to_numpy()])
    chi2, p, _, _ = chi2_contingency(table)
    lo, hi = g.row(0, named=True), g.row(-1, named=True)
    return {"test": test, "method": f"chi-square ({g.height} groups, n >= {MIN_GROUP:,})",
            "group_a": f"highest: {hi['g']}", "group_b": f"lowest: {lo['g']}",
            "value_a": hi["rate"], "value_b": lo["rate"], "diff": hi["rate"] - lo["rate"],
            "ci95_low": None, "ci95_high": None,
            "effect_size": sqrt(chi2 / table.sum()), "effect_measure": "Cramér's V", "p_value": p}


def main() -> None:
    cfg = load_config()
    out_dir = cfg.paths.reports / "analyst"

    with duckdb.connect(str(cfg.paths.warehouse), read_only=True) as con:
        cust = con.execute(f"""
            WITH spend AS (
                SELECT f.customer_key, sum(f.revenue) AS spend_365d
                FROM fact_sales f JOIN v_customer_cohort c USING (customer_key)
                WHERE f.date_key < c.first_purchase + 365
                GROUP BY f.customer_key
            )
            SELECT j.customer_key, j.first_channel, j.first_group, j.visits_365d,
                   c.fn, c.club_member_status, s.spend_365d
            FROM v_customer_journey j
            JOIN dim_customer c USING (customer_key)
            JOIN spend s        USING (customer_key)
            WHERE j.first_purchase BETWEEN DATE '{FUNNEL_FIRST[0]}' AND DATE '{FUNNEL_FIRST[1]}'
        """).pl()
        lock = con.execute("""
            SELECT cohort_month,
                   coalesce(second_purchase < first_purchase + 90, false) AS repeat_90d
            FROM v_customer_journey
            WHERE cohort_month IN (DATE '2020-03-01', DATE '2020-04-01')
        """).pl()

    repeat = (cust["visits_365d"] >= 2).to_numpy()
    channel = cust["first_channel"].to_numpy()
    club = cust["club_member_status"].to_numpy()
    fn = cust["fn"].to_numpy()
    spend = cust["spend_365d"].to_numpy()
    lock_repeat = lock["repeat_90d"].to_numpy()
    lock_month = lock["cohort_month"].dt.month().to_numpy()

    tests = [
        two_prop("1. 12-month repeat: store-first vs online-first",
                 repeat[channel == 1], repeat[channel == 2], "store-first", "online-first"),
        two_prop("2. 12-month repeat: club ACTIVE vs PRE-CREATE",
                 repeat[club == "ACTIVE"], repeat[club == "PRE-CREATE"], "ACTIVE", "PRE-CREATE"),
        two_prop("3. 12-month repeat: newsletter (fn=1) vs not",
                 repeat[fn == 1], repeat[fn == 0], "fn=1", "fn=0"),
        mann_whitney("4. 12-month spend: online-first vs store-first",
                     spend[channel == 2], spend[channel == 1], "online-first", "store-first"),
        chi_square("5. 12-month repeat by entry product group", cust["first_group"], repeat),
        two_prop("6. 90-day repeat: Mar-2020 vs Apr-2020 (lockdown) cohort",
                 lock_repeat[lock_month == 3], lock_repeat[lock_month == 4], "Mar-2020", "Apr-2020"),
    ]

    res = pl.from_dicts(tests, infer_schema_length=None)
    reject, p_adj, _, _ = multipletests(res["p_value"].to_numpy(), alpha=0.05, method="fdr_bh")
    res = res.with_columns(p_adj_bh=pl.Series(p_adj), significant=pl.Series(reject))
    shown = res.with_columns(
        pl.col("value_a", "value_b", "diff", "ci95_low", "ci95_high", "effect_size").round(4),
        pl.col("p_value", "p_adj_bh").map_elements(lambda v: f"{v:.2e}", return_dtype=pl.Utf8),
    )
    pl.Config.set_tbl_cols(14)
    pl.Config.set_fmt_str_lengths(60)
    print(shown.select("test", "group_a", "group_b", "value_a", "value_b", "diff",
                       "ci95_low", "ci95_high", "effect_size", "effect_measure", "p_adj_bh", "significant"))
    print("\nCaveat: club status and newsletter flags are recorded at the END of the data, so they may be "
          "consequences of loyalty, not causes (reverse causality). These tests show association only.")

    # ---------- A/B test design: sample size ----------
    ab = cfg.raw["ab_test"]
    base = ab["baseline_retention"]
    power_rows = []
    for mde in ab["mde_grid"]:
        h = cohens_h(base + mde, base)
        n = ceil(NormalIndPower().solve_power(effect_size=h, alpha=ab["alpha"], power=ab["power"],
                                              ratio=1.0, alternative="two-sided"))
        power_rows.append({"mde_pp": round(mde * 100, 1), "control_rate": base, "treatment_rate": base + mde,
                           "cohens_h": round(h, 4), "n_per_arm": n, "total_n": 2 * n})
    power = pl.DataFrame(power_rows)
    print(f"\nSample size per arm (alpha={ab['alpha']}, power={ab['power']}, baseline retention {base:.0%}):")
    print(power)

        # ---------- the analysis plan, run on SIMULATED outcomes ----------
    n = power.filter(pl.col("mde_pp") == round(ab["chosen_mde"] * 100, 1))["n_per_arm"][0]
    rng = np.random.default_rng(cfg.seed)

    def run_once(true_uplift: float) -> dict:
        control = rng.random(n) < base
        treatment = rng.random(n) < base + true_uplift
        return two_prop("SIMULATED A/B", treatment, control, "treatment", "control")

    sim = run_once(ab["simulated_true_uplift"])
    print(f"\nSIMULATED experiment (true uplift {ab['simulated_true_uplift']:.0%}, n={n:,} per arm):")
    print(f"  uplift {sim['diff']:+.3f} (95% CI {sim['ci95_low']:+.3f} to {sim['ci95_high']:+.3f}), "
          f"p = {sim['p_value']:.2e} -> {'ship' if sim['ci95_low'] > 0 else 'do not ship'}")

    # how often does each decision rule ship, across 1,000 simulated experiments?
    rows = []
    for true_uplift in [0.0, ab["chosen_mde"], ab["simulated_true_uplift"]]:
        runs = [run_once(true_uplift) for _ in range(1_000)]
        rows.append({
            "true_uplift_pp": round(true_uplift * 100, 1),
            "ship_rate_ci_excludes_0": np.mean([r["ci95_low"] > 0 for r in runs]),
            "ship_rate_ci_and_estimate_ge_mde": np.mean([r["ci95_low"] > 0 and r["diff"] >= ab["chosen_mde"]
                                                         for r in runs]),
        })
    print("\nShare of 1,000 simulated experiments that SHIP under each decision rule:")
    print(pl.DataFrame(rows))

    res.write_csv(out_dir / "hypothesis_tests.csv")
    write_markdown(shown.drop("method"), out_dir / "hypothesis_tests.md",
                   "Hypothesis tests (BH-corrected, first purchase 2019-03-01 to 2019-09-22)")
    write_markdown(power, out_dir / "ab_power.md", "A/B test sample size for the retention offer")


if __name__ == "__main__":
    main()
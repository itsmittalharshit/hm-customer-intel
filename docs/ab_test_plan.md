# Pre-registration: retention offer A/B test

**Hypothesis.** A retention offer sent to customers flagged by the expected-value policy increases 18-week retention.

**Population.** Active customers at a snapshot date with p(churn) × s × V − c > 0 (Module 2 policy).

**Randomisation.** Customer-level, 50/50 treatment vs holdout control, stratified by churn-risk decile.

**Primary metric.** Share of customers with ≥ 1 purchase in the 18 weeks after the snapshot.

**Secondary metrics.** Spend per customer over 18 weeks; number of purchase days.

**Guardrails.** Offer cost per retained customer; newsletter unsubscribe rate; purchases by low-risk customers who received no offer (spill-over).

**Minimum detectable effect.** +2 percentage points (from a 60% baseline).

**Sample size.** [n_per_arm from ab_power.md] per arm, α = 0.05 (two-sided), power = 0.80.

**Duration.** One snapshot cycle: assignment at the snapshot date, outcome measured 18 weeks later. No peeking at results before the end.

**Analysis.** Two-proportion z-test on the primary metric; 95% CI for the uplift; spend compared with Mann–Whitney U.

**Decision rule.** Ship if the 95% CI for the uplift excludes 0 **and** the point estimate is ≥ 2 pp. Otherwise, do not ship (or extend if the CI is wide and includes 2 pp).

**What this measures for the model.** The observed uplift ÷ the control churn rate estimates the real save rate *s*, replacing the 20% assumption in Module 2.

**Decision rule.** Ship if the 95% CI for the uplift excludes 0. Report the uplift with its CI.
The +2 pp MDE is the planning assumption for sample size (80% power at 2 pp); it is not a second
threshold on the point estimate, which would cut power to ~50% at the MDE (verified by simulation).
# Churn baselines (validation snapshot)

| model | pr_auc | roc_auc | lift_top10 | log_loss | brier |
| --- | --- | --- | --- | --- | --- |
| constant (train churn rate) | 0.453 | 0.5 | 1.0209 | 0.6916 | 0.2492 |
| rule: recency_days | 0.5986 | 0.6599 | 1.5221 |  |  |
| logistic regression (train) | 0.7163 | 0.799 | 1.9513 | 0.5332 | 0.1797 |
| logistic regression | 0.7183 | 0.7712 | 1.8213 | 0.5906 | 0.2011 |

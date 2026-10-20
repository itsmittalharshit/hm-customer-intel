# Churn: test snapshot 2020-05-14 (scored once)

| model | pr_auc | roc_auc | lift_top10 | log_loss | brier | ece | mean_pred | observed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| constant (train churn rate) | 0.4114 | 0.5 | 1.0545 | 0.6774 | 0.2422 |  |  |  |
| rule: recency_days | 0.5323 | 0.6292 | 1.5509 |  |  |  |  |  |
| logreg raw | 0.7008 | 0.7812 | 1.9994 | 0.552 | 0.1875 | 0.029 | 0.3939 | 0.4114 |
| logreg calibrated (isotonic) | 0.6977 | 0.7811 | 1.9998 | 0.561 | 0.191 | 0.0636 | 0.4749 | 0.4114 |
| lgbm raw | 0.7143 | 0.7874 | 2.0494 | 0.5433 | 0.1839 | 0.0194 | 0.392 | 0.4114 |
| lgbm calibrated (isotonic) | 0.7108 | 0.7873 | 2.049 | 0.5564 | 0.1892 | 0.0697 | 0.4809 | 0.4114 |

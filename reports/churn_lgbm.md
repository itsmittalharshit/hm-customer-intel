# LightGBM grid (validation snapshot)

| model | pr_auc | roc_auc | lift_top10 | log_loss | brier | trees | fit_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lgbm leaves=31 mcs=200 | 0.7285 | 0.7765 | 1.8595 | 0.5841 | 0.1994 | 2196 | 92 |
| lgbm leaves=63 mcs=200 | 0.7285 | 0.7764 | 1.8587 | 0.5841 | 0.1994 | 1556 | 82 |
| lgbm leaves=127 mcs=500 | 0.7288 | 0.7768 | 1.8601 | 0.5835 | 0.1993 | 684 | 55 |
| lgbm leaves=255 mcs=1000 | 0.7287 | 0.7767 | 1.8598 | 0.584 | 0.1994 | 492 | 62 |

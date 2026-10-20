# Retention targeting on validation (simulation: save rate 20%, offer cost 5% of mean spend)

| policy | targeted | share_targeted | expected_saved | realised_saved | offer_cost | expected_net | realised_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EV > 0 (value-aware) | 148324 | 0.204 | 13251.464 | 13357.2 | 2247.83 | 1575.765 | 1661.596 |
| same k, ranked by churn prob | 148324 | 0.204 | 23490.711 | 23493.4 | 2247.83 | -671.791 | -660.535 |
| top 10% by churn prob | 72533 | 0.1 | 12227.367 | 12230.8 | 1099.228 | -380.115 | -378.114 |
| target everyone | 725339 | 1.0 | 65722.6 | 65722.6 | 10992.413 | -3117.444 | -3048.542 |

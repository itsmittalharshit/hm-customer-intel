# Targeting on test (simulation: save rate 20%, offer cost 5% of mean spend)

| policy | targeted | share_targeted | expected_saved | realised_saved | offer_cost | expected_net | realised_net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EV > 0 (value-aware) | 182936 | 0.254 | 16251.877 | 14526.8 | 2449.802 | 1789.554 | 1187.367 |
| same k, ranked by churn prob | 182936 | 0.254 | 27958.347 | 27090.8 | 2449.802 | -693.649 | -728.309 |
| top 10% by churn prob | 72055 | 0.1 | 12131.051 | 12147.4 | 964.93 | -351.823 | -352.143 |
| target everyone | 720557 | 1.0 | 69298.681 | 59286.0 | 9649.397 | -1855.743 | -3304.605 |

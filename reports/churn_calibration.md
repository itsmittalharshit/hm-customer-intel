# Calibration on validation half B

| model | method | log_loss | brier | ece | mean_pred | observed |
| --- | --- | --- | --- | --- | --- | --- |
| logreg | uncalibrated | 0.5917 | 0.2015 | 0.0816 | 0.3719 | 0.4536 |
| logreg | platt | 0.5697 | 0.1943 | 0.0194 | 0.4522 | 0.4536 |
| logreg | isotonic | 0.5684 | 0.1938 | 0.0022 | 0.4522 | 0.4536 |
| lgbm | uncalibrated | 0.5848 | 0.1998 | 0.0873 | 0.3664 | 0.4536 |
| lgbm | platt | 0.5623 | 0.1915 | 0.0059 | 0.4522 | 0.4536 |
| lgbm | isotonic | 0.5622 | 0.1914 | 0.0029 | 0.4522 | 0.4536 |

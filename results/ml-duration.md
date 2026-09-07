# Duration model — training report

`python -m sanchay ml --experiment`. All figures simulated.

```
trained on 1875, tested on 625 held-out executions

DURATION
  MAE                   16.0 min
  MAE, nominal-only     24.9 min   <- the baseline we must beat
  improvement           35.7 %
  MAPE                  13.4 %
  P80 coverage          77.1 %   <- should sit near 80

OVERRUN
  AUC                  0.816
  Brier                0.150
  base rate             30.1 %

  calibration (predicted -> observed, n)
    0.01 -> 0.07  n= 125  ##
    0.04 -> 0.15  n= 125  ####
    0.12 -> 0.17  n= 125  #####
    0.40 -> 0.38  n= 125  ###########
    0.88 -> 0.74  n= 125  ######################

top features
  start_hour                 1563
  days_since_maintenance     1360
  km                         1316
  asset_age_years            1286
  month                      938
  nominal_duration_min       694
  tasks_in_block             693
  access_difficulty          589
  crew_experience_band       552
  severity                   352
```

# Asset risk model — training report

`python -m sanchay ml --risk`. All figures simulated.

The headline is not a win. Read the verdict.

```
temporal split: train months 0-17 (23004 rows), test months 18-23 (7668 rows)
base rate: 13.4% of assets develop a defect within 30 days

                                   AUC    Brier
  days since maintenance         0.827    0.100   <- the rule in use today,
                                                     fitted fairly
  gradient boosting              0.830    0.094
  -> the model does NOT rank better than the simple rule, but it is better calibrated.
     Our objective multiplies risk by criticality, so it needs a probability rather than a
     ranking - use the model for the number, and say plainly that the ordering is no better.

  calibration (predicted -> observed, n)
    0.00 -> 0.00  n= 1278  
    0.01 -> 0.03  n= 1278  #
    0.04 -> 0.05  n= 1278  #
    0.11 -> 0.11  n= 1278  ####
    0.20 -> 0.21  n= 1278  ########
    0.42 -> 0.41  n= 1278  ################

  mean |SHAP| — what actually drives the score
    overdue_ratio                1.9738
    days_since_maintenance       0.2710
    is_monsoon                   0.2614
    age_years                    0.1817
    season                       0.1338
    failures_to_date             0.1268
    annual_gmt                   0.0883
    months_since_last_defect     0.0595
```

## Why we still use the model

On **ranking** the simple rule is as good — and pretending otherwise would be
exactly the dishonesty our own plan warns about. On **calibration** the model is
better, and that is the property the optimizer actually needs: the objective
multiplies risk by criticality, so it consumes a probability. A ranking wearing
a percentage sign would silently distort every trade-off in the plan.

The baseline is fitted fairly — a one-feature logistic regression on the same
training data, producing a probability like ours does — rather than a raw ratio
scored against a probability. Rigging the baseline here would be the same thing
we refuse to do with the scheduling baselines.

The split is **temporal**: train on months 0–17, test on 18–23. Random-splitting
a time series is the commonest error in student ML and invalidates everything
downstream of it.


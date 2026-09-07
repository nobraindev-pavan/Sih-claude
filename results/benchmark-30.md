# Benchmark — 30 scenarios

10 seeds x 3 demand levels (low / normal / surge), 15-second solver limit,
one division, 7-day horizon. Every method draws from the same candidate blocks
and every plan is checked by the same hard-constraint auditor.

Reproduce: `python -m sanchay bench --scenarios 10 --time-limit 15 --jobs 4`

**All figures simulated.** Not a measured Indian Railways result.

```

done in 127s

Scenarios: 30   Methods: 4   Hard-constraint violations: 0

PER-METHOD MEANS
method                     n_blocks     train_cost  completion_pc  critical_comp  total_block_m  blocks_per_ta      objective
baseline_fcfs                 149.2         9428.9           83.0           78.6        20830.0            1.0       184670.2
baseline_corridor              54.9            0.0           60.5           41.6         6768.0            0.5       158987.4
greedy_coordinated             69.1         2104.4           82.4           66.9        10606.0            0.5       122090.8
optimizer                      77.7         4228.6           87.8           81.2        12504.0            0.5       111001.2

PAIRED: optimizer vs baseline_fcfs   (positive = optimizer better)
  metric                        mean delta          95% CI   win rate
  n_blocks                            71.4         +/- 7.4      30/30
  train_cost                        5200.3       +/- 865.3      30/30
  completion_pct                       4.9         +/- 1.5      26/30  (ties 2)
  critical_completion_pct              2.6         +/- 3.9      19/30  (ties 2)
  total_block_minutes               8326.0      +/- 1030.2      30/30
  blocks_per_task_done                 0.5         +/- 0.0      30/30
  objective                        73669.0      +/- 8415.7      30/30

PAIRED: optimizer vs baseline_corridor   (positive = optimizer better)
  metric                        mean delta          95% CI   win rate
  n_blocks                           -22.9         +/- 6.6       0/30
  train_cost                       -4228.6      +/- 1010.0       0/30
  completion_pct                      27.3         +/- 1.7      30/30
  critical_completion_pct             39.6         +/- 3.8      30/30
  total_block_minutes              -5736.0      +/- 1215.5       0/30
  blocks_per_task_done                 0.0         +/- 0.0      23/30
  objective                        47986.2      +/- 7454.2      30/30

PAIRED: optimizer vs greedy_coordinated   (positive = optimizer better)
  metric                        mean delta          95% CI   win rate
  n_blocks                            -8.6         +/- 5.0      10/30  (ties 3)
  train_cost                       -2124.2       +/- 780.7       2/30  (ties 3)
  completion_pct                       5.4         +/- 1.7      24/30  (ties 4)
  critical_completion_pct             14.3         +/- 3.6      28/30  (ties 2)
  total_block_minutes              -1898.0       +/- 878.8       6/30  (ties 1)
  blocks_per_task_done                -0.0         +/- 0.0      14/30  (ties 2)
  objective                        11089.6      +/- 3125.0      30/30

wrote out/benchmark.csv
```

# Ablations — testing our own contributions

3 seeds, 10-second solver limit. Reproduce with
`python -m sanchay ablate --seeds 3 --time-limit 10`.

**All figures simulated.** Not a measured Indian Railways result.

```
Objective values are only comparable WITHIN a study. The pareto sweep
changes the objective's own weights, so its objective column compares
plans against different yardsticks - read blocks against train cost there,
not the objective.

### coordination
  setting                   blocks  coord  blk min  train cost  done %  crit %   objective   gap %
  ------------------------------------------------------------------------------------------------
  coordination allowed        68.0   29.7    11060        2703    85.8    79.5       98953    65.4
  coordination forbidden     100.0    0.0    15400        4706    87.6    81.8      121307    59.1

### pareto
  setting                   blocks  coord  blk min  train cost  done %  crit %   objective   gap %
  ------------------------------------------------------------------------------------------------
  setup=0                     94.3   34.0    15900        5878    91.8    91.1       61163    74.1
  setup=100                   94.0   31.0    15880        5714    90.2    88.5       74229    72.9
  setup=250                   91.0   31.7    15160        5445    90.5    87.9       85862    70.8
  setup=500                   68.7   32.7    11240        3954    90.4    89.6       85214    61.5
  setup=1000                  66.0   29.3    10760        3183    86.7    86.4      123852    59.8
  setup=2000                  57.3   30.3     9500        2135    82.4    79.6      180700    57.6

### anytime
  setting                   blocks  coord  blk min  train cost  done %  crit %   objective   gap %
  ------------------------------------------------------------------------------------------------
  limit=1s                    64.3   23.3    10160        1323    81.7    67.2      111275   100.0   * warm-start fallback
  limit=3s                    63.3   24.0     9920        1303    81.3    67.7      110000    70.7
  limit=10s                   70.3   30.0    11060        2701    85.7    79.8       99947    65.7
  limit=30s                   64.0   38.0    10660        3726    93.7    95.9       70509    51.6
  * the time limit expired before the solver found anything, so these rows are the
    greedy warm start rather than an optimizer result - read them as the floor, not the method

### screening
  setting                   blocks  coord  blk min  train cost  done %  crit %   objective   gap %
  ------------------------------------------------------------------------------------------------
  keep=1                      68.7   33.0    10820         949    85.2    82.1       95451    55.9
  keep=2                      69.3   31.7    11000        3139    88.5    83.5       92832    63.0
  keep=4                      85.7   25.7    13320        8231    95.4    91.7       94848    67.6
  keep=8                      91.0   23.7    14200       12115    98.3    96.9       94520   100.0   * warm-start fallback
  * the time limit expired before the solver found anything, so these rows are the
    greedy warm start rather than an optimizer result - read them as the floor, not the method

### durations
  setting                   blocks  coord  blk min  train cost  done %  crit %   objective   gap %
  ------------------------------------------------------------------------------------------------
  nominal                     65.0   32.3    10500        3402    86.9    84.0       90753    62.9
  model P80                   79.0   33.0    13160        4956    90.9    89.5       95121    61.0


```

## What each study says

**coordination** — the core idea, isolated. The solver keeps the same candidate
blocks, the same rulebook and the same objective, and loses only the ability to
put more than one department in a window. Result: **100 blocks instead of 68**
and **4,706 weighted train-minutes instead of 2,703**.

Note what does *not* move: completion is essentially unchanged (87.6% against
85.8%). Coordination is not how the work gets done — it is how the work gets
done with fewer disruptions and less traffic displaced. Claiming it lifts
completion would be claiming something this experiment does not show.

**pareto** — the block setup cost swept from 0 to 2000 traces a clean monotone
frontier, 94 blocks at 5,878 train-minutes down to 57 blocks at 2,135. Every
point is a legitimate plan. This is the argument that the objective is a
trade-off surface a division can choose a point on, not a number tuned until it
flattered us. Objective values are *not* comparable across this study — the
sweep changes the objective's own weights, so read blocks against train cost.

**anytime** — 3s: objective 110,000. 10s: 99,947. 30s: 70,509. The one-second
row is the warm-start fallback, not an optimizer result. This is why the demo
uses 15–20 seconds rather than asserting that ten is enough, and why the
reported optimality gap stays large: we are trading proof for a good incumbent,
deliberately, and saying so.

**screening** — candidate pre-screening, our documented heuristic. `keep=1`
gives the lowest train cost (949) because it only ever offers the cheapest
window; `keep=4` gives the highest completion (95.4%) because more choice fits
more work, at 8,231 train-minutes. `keep=8` overflows the budget and falls back.
The shipped default of 2 sits in the middle, and the cost of that choice is
visible here rather than hidden.

**durations** — planning to the model's P80 rather than nominal buys +4pp
completion and +5.5pp on critical work, for 14 more blocks and more displaced
traffic. Longer sanctioned windows are the price of not overrunning them; the
execution-side half of this trade is in `results/ml-duration.md`.

# 05 · The optimizer — CP-SAT model specification

This is the project. Everything else is input preparation or output rendering. Assign your
strongest logical thinker here, and have them do the OR-Tools job-shop tutorial until they
can modify it from memory (doc 9).

## The key modelling decision

The concept note proposed `X(task, time, corridor)`. **Do not.** With 200 tasks × 672
fifteen-minute slots × 16 sections that is ~2.1 million booleans, and "minimise the number
of separate blocks" is awkward to express over it.

Instead: **the block is the decision object.**

Enumerate candidate blocks (a section × a time window). Each gets a boolean `open[b]`.
Tasks are assigned into open blocks. Then:

- *"Minimise separate disruptions"* is literally `minimise Σ_b open[b]`.
- **Coordination is emergent.** Nobody writes a rule saying "combine departments." The
  solver combines them because opening a second block costs more than packing into the
  first. That is a much better story than a hand-written merge heuristic, and it is true.
- The model is a **bin packing with setup cost** — a well-studied structure CP-SAT is
  excellent at.

Model size drops to a few thousand booleans and it solves in seconds.

## Sets

| Symbol | Meaning | Size |
|---|---|---|
| `T` | maintenance tasks in the horizon | ~200 |
| `S` | block sections | ~15 |
| `W` | candidate windows per section (corridor windows + timetable gaps) | ~7–20 per section per week |
| `B` | candidate blocks = feasible (section, window) pairs | ~150–300 |
| `R` | crews | ~20 |
| `F(t)` | blocks task *t* could legally go in | ~3–15 per task |

**`F(t)` is the most important precomputation in the project.** A pair `(t, b)` is feasible
only if all of: `b.section` covers `[t.km_from, t.km_to]`; `b.duration ≥
t.predicted_duration_min`; `b.end ≤ t.due_date`; and the rulebook does not have `t` forbid a
permit `b` must hold. Building `F(t)` in Python before the solver starts prunes the model by
one to two orders of magnitude. Do this first; measure it; put the number on a slide.

## Variables

```python
open[b]        ∈ {0,1}                      # block b is opened
x[t,b]         ∈ {0,1}   for b in F(t)      # task t is done in block b
unsched[t]     ∈ {0,1}                      # task t is not scheduled  (SLACK - see below)
itv[t,b]       = NewOptionalIntervalVar(start, dur, end, x[t,b])   # within b's span
kmv[t,b]       = NewOptionalIntervalVar(km_lo, km_len, km_hi, x[t,b])  # 1-D "km axis"
crew_itv[t,b]  = same interval, tagged to t's assigned crew
```

The `kmv` trick is worth understanding: model each task's *physical extent along the track*
as an interval on a kilometre axis, then `AddNoOverlap` those intervals within each block.
That is exactly "two gangs cannot occupy the same metres," expressed in one line, and it is
what lets the solver decide that Engineering at KM 120–125 and TRD at KM 130 can share a
window while Engineering at KM 120–125 and S&T at KM 123 cannot work simultaneously (though
they may still share the block if sequenced in time). Inflate each interval by
`min_separation_m` from the rulebook.

## Hard constraints

```python
# 1. every task is scheduled, or explicitly not (never let the model be INFEASIBLE)
for t in T:
    model.Add(sum(x[t,b] for b in F(t)) + unsched[t] == 1)

# 2. a task can only go in an open block
for t, b in pairs:
    model.Add(x[t,b] <= open[b])

# 3. a block with no tasks is not open (prevents phantom blocks)
for b in B:
    model.Add(open[b] <= sum(x[t,b] for t in T_of(b)))

# 4. tasks fit inside their block's time span
    itv[t,b] start >= b.start ; end <= b.end          # enforced by interval bounds

# 5. physical separation inside a block
for b in B:
    model.AddNoOverlap([kmv[t,b] for t in T_of(b)])

# 6. permit compatibility  (rulebook)
#    block permit set = union of its tasks' requirements
for b in B:
    for permit in ALL_PERMITS:
        for t in T_of(b):
            if permit in t.requires:  model.Add(permit_held[b,permit] >= x[t,b])
        for t in T_of(b):
            if permit in t.forbids:   model.Add(x[t,b] + permit_held[b,permit] <= 1)

# 7. explicit incompatible pairs from the rulebook
for b in B:
    for (t1, t2) in incompatible_pairs_in(b):
        model.Add(x[t1,b] + x[t2,b] <= 1)

# 8. one block at a time per section
for s in S:
    model.AddNoOverlap([block_itv[b] for b in B_of(s)])   # optional intervals on open[b]

# 9. network: never block a section and its diversionary route simultaneously
for (s, d) in diversion_pairs:
    model.AddNoOverlap([block_itv[b] for b in B_of(s)] + [block_itv[b] for b in B_of(d)])

# 10. crew capacity and travel
for r in R:
    model.AddNoOverlap([crew_itv[t,b] for t,b in pairs if crew_of(t) == r])
    # plus: forbid same crew in two blocks closer than travel time
    for (t1,b1),(t2,b2) in crew_conflicting_pairs(r):
        model.Add(x[t1,b1] + x[t2,b2] <= 1)

# 11. task dependencies (e.g. survey before renewal)
for (a, b_task) in dependencies:
    model.Add(end_time(a) <= start_time(b_task))

# 12. policy caps
for b in B:
    model.Add(block_duration[b] <= MAX_BLOCK_MIN)         # e.g. 240
model.Add(sum(open[b] for b in B_on_day(d)) <= MAX_BLOCKS_PER_DAY)
```

### Constraint 1 is a demo-safety feature, not a modelling nicety

`unsched[t]` with a large penalty means **the model can never return INFEASIBLE.** On stage,
in front of judges, with a scenario someone just perturbed in the what-if panel, an
INFEASIBLE result is a catastrophe and a heavily-penalised soft failure is a graceful
degradation you can *narrate*: "under this much extra freight, four low-priority jobs no
longer fit — here they are, and here is what they'd cost to force in." That turns a failure
mode into a feature. Build it in from day one.

## Objective

Precompute per-block constants in Python (see below), then:

```
minimise
    W_TRAIN     * Σ_b open[b] * train_cost[b]
  + W_SETUP     * Σ_b open[b]                       # the coordination driver
  + W_DOWNTIME  * Σ_b open[b] * duration_min[b]
  + W_OVERDUE   * Σ_t unsched[t] * priority[t] * max(0, days_overdue[t])
  + W_RISK      * Σ_t unsched[t] * risk[t] * criticality[t]
  + W_NIGHT     * Σ_b open[b] * night_penalty[b]    # night work costs more, is less safe
```

Suggested starting weights: `W_TRAIN=1, W_SETUP=500, W_DOWNTIME=2, W_OVERDUE=50,
W_RISK=200, W_NIGHT=20`. Expose all six as sliders in the UI — letting a judge move
`W_SETUP` and watch blocks merge and train cost rise is one of the best 20 seconds in the
demo, and it proves the objective is real rather than decorative.

Note there is no explicit "maximise utilisation" term. Utilisation is implied: minimising
`Σ open[b] × duration[b]` while scheduling the same work *is* maximising utilisation.
Report it as a KPI; don't put it in the objective twice.

## The precomputation that makes it fast

**`train_cost[b]` is a constant.** For candidate block `b` on section `s` over `[t1, t2]`,
compute it in Python before the model is built:

```python
def train_cost(section, t1, t2, line_type):
    affected = [p for p in train_paths[section]
                if overlaps(p.arrival, p.departure, t1, t2)]
    if line_type == "double":
        # single-line working: trains pass at reduced capacity
        return sum(p.train.priority_weight * SINGLE_LINE_DELAY_MIN for p in affected)
    else:
        # single line: total closure, trains are detained or cancelled
        return sum(p.train.priority_weight * detain_or_cancel_cost(p, t1, t2)
                   for p in affected)
```

Suggested class weights: Vande Bharat / Rajdhani **10**, Mail-Express **6**, Passenger/MEMU
**3**, Freight **2** (freight is low-priority for punctuality but high for revenue — say so
if asked, and offer it as a tunable). Corridor-policy windows have `train_cost ≈ 0` by
construction, which is exactly why the policy exists and why the optimizer will naturally
prefer them.

Doing this outside the solver is the difference between a 4-second solve and a 4-minute one.

## Solving

```python
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 10.0        # 30 for benchmarks
solver.parameters.num_search_workers = 8
solver.parameters.log_search_progress = True        # screenshot this for the deck
status = solver.Solve(model)
```

Always report `status`, `ObjectiveValue()`, `BestObjectiveBound()` and the gap. Showing a
0.0% optimality gap on a real instance is a strong, checkable claim — far better than
"our AI found the best schedule."

## Explainability, done with the solver instead of prose

Three layers, in increasing order of impressiveness:

**1. Cost decomposition.** Every block carries its six objective contributions. The
"why this block?" panel is a bar chart of them. No text generation, no hallucination risk.

**2. Counterfactual re-solve — "Why not Tuesday 14:00?"**
```python
model2 = model.Clone()
model2.Add(x[task, alternative_block] == 1)
status2 = solver.Solve(model2)
# INFEASIBLE -> a hard constraint forbids it; name which (see 3)
# FEASIBLE   -> report objective2 - objective1, decomposed:
#               "that window costs 340 more train-minutes and opens a 4th block"
```
This is the single most impressive thing in the demo, because it answers the planner's
actual question with a number rather than an assertion.

**3. Naming the binding constraint.** *(Implemented differently — see
[`build-notes.md`](build-notes.md) §6.)* The shipped code checks the common
objections directly in Python before touching the solver: wrong section, window
too short, past the deadline, section already blocked, an incompatible activity
already in that window. Those cover the cases planners actually ask about and
give an instant, specific answer. CP-SAT assumptions
(`AddAssumptions` + `SufficientAssumptionsForInfeasibility`) remain a worthwhile
November upgrade for the residual cases. Either way the output is a sentence
like:
*"14:00 Tuesday is not possible: TRD gang 3 is committed at KM 40 until 15:20, and the S&T
point overhaul requires 50 m separation from the tamping worksite."*

That sentence, generated from the solver, is worth more than the entire rest of the UI.

## Validation — prove the model is right, not just fast

Write these as tests in week 2. They are cheap and they catch the bugs that would otherwise
surface on stage:

1. **Trivial instance:** one task, one window → one block containing it.
2. **Forced coordination:** three tasks, same section, same window, all compatible → exactly
   one block. If you get three, constraint 2 or the setup cost is wrong.
3. **Forced separation:** two incompatible tasks, one window → two blocks or one deferred.
4. **Permit conflict:** a `forbids: power_block` task and a `requires: power_block` task can
   never share a block.
5. **Deadline:** a task due Monday is never scheduled Tuesday.
6. **Never infeasible:** a wildly over-constrained instance returns a plan with `unsched`
   tasks, not `INFEASIBLE`.
7. **Determinism:** same seed, same weights → byte-identical plan. (Fix `random_seed` and
   `num_search_workers=1` for this test.)
8. **Monotonicity:** raising `W_SETUP` never increases the block count.

Test 8 is the kind of property test that makes a technical judge sit up.

## Performance targets

| Instance | Tasks | Target solve | Hard limit |
|---|---|---|---|
| Demo weekly | ~60 | < 3 s | 10 s |
| Full weekly | ~200 | < 10 s | 30 s |
| Monthly | ~800 | < 60 s | 120 s |

If the monthly horizon is slow, solve it **week by week with carry-over** rather than
fighting the solver. A rolling-horizon decomposition is standard practice, is honest, and
is easy to explain. Do not spend a week tuning CP-SAT parameters; spend an hour on
decomposition instead.

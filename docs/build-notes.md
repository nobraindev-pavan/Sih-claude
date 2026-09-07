# Build notes — where the code departs from the plan

The plan was written before the code. Some of it turned out to be wrong, and
this file records the differences so nobody trusts a document over the source.
Each entry is a decision a judge might ask about.

## 1. Candidate blocks span the whole horizon, not just quiet windows

**Plan said:** generate candidate windows from corridor policy and timetable gaps.

**Code does:** enumerate candidate blocks across the whole horizon and price each
one's train disruption.

**Why:** the first version only offered train-free windows, so `train_cost` was
zero for every candidate and the disruption term in the objective was dead — the
number a railway operator cares about most had no effect on any decision. A block
*can* be taken through traffic; the controller regulates trains around it. Making
that possible, and charging for it, is what gives the optimizer something real to
trade off. Corridor windows still come out cheapest, which is exactly the
behaviour we want to *emerge* rather than hard-code.

## 2. Corridor candidates are generated separately from the grid

The general start grid is coarse (180 min) to keep near-duplicate candidates from
swamping the search with symmetry. But a coarse grid does not land on 10:00 by
accident, so almost no candidate aligned with the mandated corridor window — which
silently crippled the corridor baseline and hid the cheapest windows in the whole
division from every scheduler. Corridor candidates are now generated on their own
offsets and never pruned. See `build_candidate_blocks` in `core/candidates.py`.

## 3. Pre-screening is a documented heuristic

We keep the `keep_per_slot` cheapest candidates per (section, day, duration).
Two, tuned. Raising it gives the solver more choice but adds symmetric candidates
that cost more search time than they win. **This means the optimality gap we
report is against the pre-screened model, not the full one.** Say so if asked;
`CandidateConfig(keep_per_slot=999)` recovers full enumeration.

## 4. The solver is warm-started from a greedy plan

Without an incumbent, CP-SAT spends its whole time limit finding any feasible
plan and the result is markedly worse. `baselines/greedy.py` produces the hint
and doubles as an ablation: the gap between it and CP-SAT isolates what the
*solver* contributes as opposed to what mere coordination contributes.

## 5. Blocks are charged for the whole sanctioned window

An early version trimmed each block to the minutes actually worked. That is wrong
railway semantics — traffic is regulated around the requisitioned period, so
finishing early does not un-delay the trains — and it made the comparison unfair,
because the greedy schedulers were trimmed and the solver was not. Now nothing
trims, and the greedy schedulers instead *downsize* to the shortest candidate
window that holds their work, which is what a real planner would requisition.

## 6. Explanations use static diagnosis plus a re-solve, not solver assumptions

**Plan said:** use `SufficientAssumptionsForInfeasibility()`.

**Code does:** check the common objections in Python first (wrong section, window
too short, past the deadline, section already blocked, an incompatible activity
already in the window), then clone the model, force the alternative and re-solve
for the cost delta.

**Why:** the Python checks give a specific, plain-English answer instantly for the
cases planners actually ask about, and they are far easier for the team to
maintain and explain. The assumptions API remains a worthwhile November upgrade
for the residual cases — it is not needed for the ones that come up.

## 7. Plan stability is an objective term

Not in the plan at all. Re-optimising after a what-if produced a *different*
optimum, moving 85–147 tasks — useless to a planner who has circulated a block
plan and wants the smallest change that absorbs the disruption. Passing the
previous plan as an `anchor` penalises every task that leaves the window it was
sanctioned in. The same perturbations now move 2–8 tasks. See
`Weights.stability`.

## 8. Crews are a cumulative resource, not individuals

Tasks carry a `crew_type`, and the model limits how many jobs of that type run at
once via `AddCumulative`, plus a fixed mobilisation allowance around each job.
Individual crew assignment with real travel times between sections is not
modelled. It is a genuine simplification; say so rather than implying otherwise.

## 9. The ML layer is data and specification, not a trained model

`gen/execution_log.py` produces 2,500 historical block executions from a process
deliberately unlike anything a gradient-boosting model would fit — multiplicative
interactions, a congestion effect, unobserved crew skill, a heavy right tail from
discrete disruptions. Calibrated to a ~30% overrun rate. `Task` already carries
`predicted_duration_min` and `overrun_probability`, and the optimizer plans to
the former. **Training the model is the ML seat's Phase 2 work** (doc 6); until
then the prediction falls back to the nominal duration.

## 10. Every derived solve reuses the base plan's time budget

The API originally gave the base plan 12 seconds and each what-if 15. The
what-if then "improved" the plan - fewer deferred tasks after withdrawing a
gang - because the extra three seconds of search outweighed the disruption. A
comparison between two solves with different budgets measures the budget.
`Session.time_limit` is now the single budget for the base plan, every
counterfactual and every what-if. This is the easiest way to lie with this tool;
check it first if a what-if result looks too good.

## 11. Concurrent requests for one world are serialised

The UI asks for the scenario, the plan and the comparison in parallel. Without a
per-key build lock all three started their own solve of the same world, competed
for CPU, and a badly under-converged plan won the cache - 43 deferred tasks
instead of 16. It looked like the optimizer being bad; it was three of them
fighting. `PlanningService` now holds a lock per scenario key while building.

## 12. Counterfactuals report a negative delta honestly

Forcing an alternative window sometimes finds a plan *better* than the one
recommended, because the base solve was not proven optimal inside its time
limit. The explanation says exactly that rather than hiding it behind a signed
number. It is what the reported optimality gap means, and a planner who catches
the system glossing over it will not trust the rest of it.

## 13. The ML model needs plan-level features it cannot have yet

`tasks_in_block` and `start_hour` are properties of the *plan*, but we need
durations to build the plan. `apply_predictions` breaks the loop with a stated
planning assumption (a typical block holds two jobs, in the corridor window).
Iterating - predict, plan, re-predict with the realised block composition - is a
clean Phase 3 improvement, not a fix for a bug.

# 07 · Evaluation — how we prove we are better

The concept note is right that a winning prototype must quantify improvement against a
baseline. This document specifies the experiment precisely enough that the result is
believable.

## Two baselines, not one

**B1 — Departmental FCFS.** Models uncoordinated requisitioning, the "before" story.

```
for dept in [ENG, TRD, SNT]:                 # rotate the order across scenarios
    for task in sorted(dept.tasks, key=(severity, due_date)):
        for window in earliest_first(candidate_windows(task.section)):
            if section_free(window) and train_cost(window) < THRESHOLD:
                grant_block(task, window); break
```
No cross-department combining except by coincidence. Beating B1 shows the problem is real.

**B2 — Corridor-policy greedy.** *This is the baseline that matters.*

All work is forced into the mandated three-hour daily corridor window per section, packed
greedily by priority until the window is full, with no cross-department optimisation and no
choice of window. This models **current best practice on Indian Railways**, and beating it
honestly is our actual claim.

Most teams will only build B1 and beat a strawman. Building B2 — and admitting it is a
strong baseline — is a differentiator with any judge who knows the domain.

**Fairness rules, stated on the slide.** Same scenario, same rulebook, same safety
constraints, same crews, same durations. The baselines are not allowed to violate any
constraint the optimizer must respect. A baseline that cheats invalidates everything.

## Metrics

| Metric | Direction | Definition |
|---|---|---|
| **Separate blocks** | ↓ | count of distinct block events — our headline |
| **Total block minutes** | ↓ | Σ block durations (line-occupancy cost) |
| **Weighted train disruption** | ↓ | Σ priority_weight × delay minutes, incl. downstream |
| **Trains affected** | ↓ | count, split by class |
| **High-priority completion** | ↑ | % of critical tasks done by due date |
| **Residual overdue risk** | ↓ | Σ risk × criticality over unscheduled tasks |
| **Block utilisation** | ↑ | productive work minutes ÷ sanctioned block minutes |
| **Overrun rate** | ↓ | % of blocks exceeding their window (the ML metric) |
| **Solve time** | — | seconds, reported honestly |

Headline for the pitch: **separate blocks** and **weighted train disruption**. Those two are
what a DOM actually cares about, and they are where coordination pays.

## Protocol

- **30 seeded scenarios × 3 demand levels** (low / normal / surge) = 90 runs per method.
- Same seeds across all three methods → **paired comparison**, which is far more powerful
  than comparing group means.
- Report **mean ± 95% CI of the paired per-scenario delta**, not two averages side by side.
- Report the **win rate**: "the optimizer produced fewer separate blocks in 87 of 90
  scenarios" is a more persuasive sentence than any percentage.
- One command reproduces everything: `python -m eval.harness --scenarios 30 --out report/`.

## Ablations — where the credibility is

Run each of these and put the table in the appendix of the deck. Ablations show you tested
your own contributions rather than assuming them:

1. **No coordination** — forbid multi-department blocks. Isolates the value of the core idea.
2. **Nominal vs predicted vs P80 durations** — isolates the value of the ML layer (doc 6).
3. **Weight sensitivity** — sweep `W_SETUP` from 0 to 2000; plot blocks vs train cost. This
   is a **Pareto frontier**, and showing one is a genuinely graduate-level move.
4. **Time-limit sensitivity** — objective at 1 s / 5 s / 30 s. Shows we know about anytime
   behaviour and that the demo's 10 s limit is a defensible choice.
5. **Horizon** — weekly-only vs rolling monthly. Justifies the decomposition.

## Report the trade-off. Deliberately.

Find the metric where the optimizer is *worse* — most likely total block minutes, because
combining work into one longer window can raise line-occupancy even as it slashes the number
of disruptions and the train cost — and **put it on the slide**.

> "Our plan uses 6% more total block minutes than the FCFS baseline, but 58% fewer separate
> blocks and 41% lower weighted train disruption. That trade is deliberate: one 180-minute
> coordinated block costs the section far less than three 70-minute blocks, because every
> block has fixed overheads — protection, caution orders, and the trains held at either end."

Volunteering a trade-off you understand and can justify builds more credibility with a
technical judge than a clean sweep. A clean sweep on every metric invites the suspicion that
the baseline was rigged.

## Honesty rules (from the concept note — keep them)

- Every figure carries the label **"simulated — Vijaypur synthetic division, 30 scenarios."**
- Never quote a number as a real railway result.
- Report solver status and optimality gap, not just the objective.
- If a run is cherry-picked for the demo, say it is a representative scenario and show the
  distribution behind it.

## What goes in the deck

1. One paired-delta bar chart: three methods × three headline metrics, with CIs.
2. One Pareto frontier: blocks vs train disruption as `W_SETUP` varies.
3. One before/after train graph — the same day, B2 vs optimized, blocks drawn as rectangles.
4. One table: the full metric matrix with means ± CI and win rates.

Chart 3 is the emotional one and it is the slide judges will remember. Chart 2 is the one
that convinces the technical judge you are not a dashboard.

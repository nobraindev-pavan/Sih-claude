# SANCHAY

**Section-level Analytics & Coordinated Block Planning Engine**
SIH 2026 · Problem statement **SIH26027** · Ministry of Railways

> Indian Railways keeps three hours of every section vacant every day for
> maintenance — that is Railway Board policy. Filling those three hours is still
> a human job: Engineering, S&T and Traction Distribution each raise their own
> block demands, and a Section Controller reconciles them by phone, section by
> section.
>
> This is the missing decision layer. It takes the demands BDMS already collects
> and the train chart COA already produces, and solves for the smallest set of
> safe, coordinated blocks that clears the most critical work at the lowest cost
> in train minutes. Every recommendation comes with the reason it was chosen and
> what choosing otherwise would have cost. **A planner still sanctions it.**

## Quickstart

```bash
pip install -r requirements.txt

python -m sanchay gen          # build the synthetic Vijaypur division
python -m sanchay plan         # run every method, compare, draw the train graph
python -m sanchay explain      # why this block, and why not that one
python -m sanchay whatif       # perturb an assumption and re-optimise
python -m sanchay bench        # the full 30-scenario benchmark
python -m pytest tests/ -q     # 41 tests, including the solver validation suite
```

`python -m sanchay plan` writes `out/compare.html` — open it in a browser. No
server, no network, no build step.

## What it does

```
TMS / SMMS / TDMS  ──┐
   (maintenance)     │
                     ├──► unified schema ──► candidate blocks ──► CP-SAT ──► plan
COA (train chart) ───┤        + safety           + precomputed      + explanations
                     │         rulebook           train cost         + what-if
BDMS (requisitions) ─┘
```

1. **Ingest** three departmental backlogs and a train chart through a connector
   interface (`sanchay/core/connectors/`). CSV today; the API stubs carry the
   real field mapping in [`docs/field-mapping.md`](docs/field-mapping.md).
2. **Enumerate candidate blocks** — a section × a window — and price each one's
   train disruption *before* the solver runs. That precomputation is what makes
   it solve in seconds.
3. **Solve.** CP-SAT picks which blocks to open and packs tasks into them,
   subject to the safety rulebook, physical separation, crew capacity, section
   exclusivity and deadlines.
4. **Explain.** Every block carries its objective decomposition, and any
   alternative window can be costed by forcing it and re-solving.
5. **Re-plan.** Change an assumption and the plan re-forms — minimally, because
   the previous plan anchors the objective.

## The modelling decision that matters

**The block is the decision object, not the task.** We enumerate candidate
blocks, give each an `open[b]` boolean, and assign tasks into them. So:

- "minimise the number of separate disruptions" is literally `sum(open[b])`;
- **coordination is emergent** — nothing in the code says "combine departments";
  the solver combines them because opening a second block costs more than
  packing into the first;
- the model is a bin-packing-with-setup-cost, which CP-SAT is good at.

Indexing by `(task, time, section)` instead — the obvious first idea — is about
2.1 million booleans at this scale and makes the headline objective awkward to
express. See [`docs/05-optimizer.md`](docs/05-optimizer.md).

## Results

**30 scenarios** — 10 seeds x 3 demand levels (low / normal / surge), 15-second
solver limit. One division, one week: 16 block sections, ~1,280 assets, 108–270
open maintenance tasks across three departments, 672 train paths. Means across
all 30 runs, not a favourable seed:

| | separate blocks | coordinated | block minutes | train cost | work done | critical done |
|---|---|---|---|---|---|---|
| **B1** uncoordinated (FCFS) | 149.2 | 0 | 20,830 | 9,429 | 83.0% | 78.6% |
| **B2** corridor policy | 54.9 | — | 6,768 | 0 | 60.5% | 41.6% |
| greedy coordination | 69.1 | — | 10,606 | 2,104 | 82.4% | 66.9% |
| **SANCHAY** | 77.7 | — | 12,504 | 4,229 | **87.8%** | **81.2%** |

Paired per-scenario deltas, with 95% confidence intervals and win rates —
paired because the same seed produces the same world for every method, which is
a far stronger comparison than two group means:

| vs **B1** uncoordinated | mean delta | 95% CI | wins |
|---|---|---|---|
| separate blocks | **−71.4** | ± 7.4 | 30/30 |
| weighted train disruption | **−5,200** | ± 865 | 30/30 |
| total block minutes | −8,326 | ± 1,030 | 30/30 |
| work completed | +4.9 pp | ± 1.5 | 26/30 |
| objective | −73,669 | ± 8,416 | 30/30 |

| vs **B2** corridor policy | mean delta | 95% CI | wins |
|---|---|---|---|
| work completed | **+27.3 pp** | ± 1.7 | 30/30 |
| critical work completed | **+39.6 pp** | ± 3.8 | 30/30 |
| objective | −47,986 | ± 7,454 | 30/30 |
| separate blocks | *+22.9* | ± 6.6 | 0/30 |
| weighted train disruption | *+4,229* | ± 1,010 | 0/30 |

Read it honestly, because this is how it should be presented:

- **Against uncoordinated requisitioning** we cut separate disruptions by 47%
  and weighted train disruption by 55%, while completing *more* work — winning
  on every headline metric in all 30 scenarios.
- **Against current best practice** (B2, everything packed into the mandated
  corridor window) we complete 88% of the backlog instead of 60%, and 81% of the
  critical work instead of 42%, in every single scenario.
- **The trade-off, stated before anyone asks:** to do that we open ~23 more
  blocks and displace more traffic than B2. B2 keeps its block count and train
  cost low by *simply not doing the work* — it leaves 40% of the backlog and
  nearly 60% of critical jobs undone, because the corridor window alone cannot
  absorb them. Choosing to take a block outside the corridor window when a
  critical defect needs one is the deliberate trade, and it is what decision
  support means here.
- **Zero hard-constraint violations** across all 120 plans. Every plan from every
  method is audited by `sanchay/eval/metrics.py:validate`.

Full output and the per-scenario CSV: [`results/`](results/). Reproduce with
`python -m sanchay bench`; a single run is `python -m sanchay plan --seed 1`.

**Every figure here is simulated.** The data is schema-compatible with TMS,
SMMS, TDMS and COA; it does not come from them, and none of these numbers is a
measured railway result.

## Repository

```
sanchay/
  core/         schema, rulebook, windows, traffic cost, candidates, connectors
  gen/          seeded synthetic division + historical execution log
  optimizer/    cpsat.py (the model), explain.py, whatif.py
  baselines/    fcfs.py (B1), corridor.py (B2), greedy.py
  eval/         metrics.py (incl. the hard-constraint auditor), harness.py
  viz/          traingraph.py - the time-distance chart, hand-rolled SVG
  cli.py
data/
  rulebook.yaml        the safety rules - permits, compatibility, separation
  scenarios/           generated CSV fixtures
docs/                  the plan: critique, domain, architecture, roadmap
tests/                 41 tests
```

## Safety, and what this is not

- It is **not** an autonomous controller. A human sanctions every block.
- Every safety rule is a **hard constraint** the solver cannot trade against
  cost, and it lives in a reviewable file (`data/rulebook.yaml`) rather than
  buried in code.
- That rulebook is **derived from published sources and simplified for the
  prototype**. It has not been reviewed by a serving railway officer. Getting it
  reviewed is the highest-value open item — see
  [`docs/02-domain-primer.md`](docs/02-domain-primer.md).
- The plan is auditable: every block records the objective terms that paid for
  it and the trains it displaces.

## Where to start reading

New to the project? [`docs/`](docs/) has the full plan, in order. If you are
about to write code, the two that matter are
[`docs/04-architecture.md`](docs/04-architecture.md) (the data model — the
contract everything depends on) and
[`docs/05-optimizer.md`](docs/05-optimizer.md) (the solver).

If you are new to programming, start at
[`docs/09-learning-path.md`](docs/09-learning-path.md). One rule from it applies
to everyone: **never merge code you cannot explain line by line.** Judges will
point at a line and ask.

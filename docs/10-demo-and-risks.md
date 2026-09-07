# 10 · Demo script, judge Q&A, and the risk register

## The seven-minute demo

Rehearse this until it is muscle memory. Time every section. The demo is the deliverable
that judges actually score.

**0:00 — The hook. One concrete story, no slides.**
> "Last month on this section, three departments asked for three separate blocks — in the
> same week, within five kilometres of each other. Six hours of line closure and fourteen
> trains delayed, to complete two hours and forty minutes of actual work. Nobody did
> anything wrong. Engineering, S&T and Traction each raised a correct requisition, and no
> one system was looking at all three."

**0:45 — Current practice, on the train graph.** Show the corridor-policy baseline plan for
one week on the Vijaypur division. Diagonal train paths, block rectangles scattered across
sections. Point at the three blocks in the hook. Let them look at it for a beat.

**2:00 — The inputs.** "187 open tasks from TMS, SMMS and TDMS in our unified schema. 120
train paths from the COA chart. Our safety rulebook — sixteen activity types, their permits,
and which may share a window." Show the rulebook YAML for three seconds. Real file, real
constraints.

**2:45 — The engine, briefly.** Risk score → priority → feasible (task, block) pairs → CP-SAT.
Show the solver log for two seconds. "3,140 booleans, solved to optimality in 4.2 seconds."
Do not explain the model. If they want it, they will ask, and then you get to shine.

**3:30 — The result, on the same graph.** Same week, same tasks. The three blocks from the
hook are now one. KPI strip: separate blocks 31 → 13, weighted train disruption down 41%,
high-priority completion 78% → 96%. Every number labelled *simulated*.

**4:15 — "Why this block?"** Click the coordinated block. Cost decomposition bar chart. Then
the counterfactual: click *"why not Tuesday 14:00?"* →
> *"Tuesday 14:00 is possible but costs 340 more weighted train-minutes — two Mail-Express
> paths cross that window. It would also open a fourth block on the branch, because TRD gang
> 3 cannot reach KM 40 in time."*

**Pause here.** This is the moment the demo is won. Let it land.

**5:15 — What-if.** "The Divisional Operating Manager gets a message: an extra rake of coal
on Thursday, and a track gang is unavailable." Toggle both. Re-solve on screen. Show the
plan diff — what moved, what stayed, what could not be accommodated and what it would cost
to force it in.

**6:00 — The evidence.** The 30-scenario benchmark chart. Mean ± CI, paired deltas, win
rate. Then say the trade-off out loud before anyone asks:
> "We use 6% more total block minutes than the uncoordinated baseline. That is deliberate —
> one long coordinated block costs the section less than three short ones, because every
> block carries fixed overheads."

**6:45 — The close.** "Everything you saw runs against a connector interface. Point it at
BDMS and COA and the only thing that changes is one class per source. The planner still
sanctions every block. We are not replacing the controller — we are giving them a plan worth
reviewing."

### Demo hygiene

- Everything **offline**. No CDN, no live API, no npm install on the day.
- A **fixed demo scenario**, pre-solved and cached, plus a live solve you can trigger.
- **Never let it be INFEASIBLE** — the `unsched` slack from doc 5 guarantees this.
- Two laptops, identically configured, both tested on the projector.
- The backup video ready in a browser tab, one click away.
- Whoever is on the keyboard is not the one talking.
- Big fonts. Projectors are terrible and the back row is where the judge sits.

## The questions you will be asked

Rehearse these answers. Assign each to a specific person.

**"BDMS already exists. What are you adding?"** → Doc 1. BDMS routes and records decisions;
it does not make them. We are the decision layer, using the same fields.

**"There is already a three-hour corridor block policy."** → We assume it. The policy says
*when*; we decide *what goes in*. Corridor windows are our preferred window class and our
strongest baseline.

**"Where did your data come from?"** → A synthetic division we generated, field-compatible
with TMS/SMMS/TDMS/COA. We did not have and did not claim access to operational systems.
Here is the field mapping document.

**"Is this safe? Would you let an AI schedule track work?"** → No, and we did not build that.
Every safety rule is a hard constraint the solver cannot violate, the rulebook is a
reviewable file, and a human sanctions every block. It is decision support with an audit
trail.

**"Why not deep learning / a GNN?"** → Doc 6. We have no real operational history; a learned
model fitted to our own simulator would recover our own assumptions with less transparency.
In a safety-critical planning context we chose the explainable mechanism. With three years of
real COA data a learned delay model is the natural next step, and it plugs into the same
interface.

**"Does it scale to a zone? To all of Indian Railways?"** → Blocks are planned per division,
and divisions are nearly independent — the coupling is at junction stations and shared
diversionary routes. So it decomposes: solve per division in parallel, with a coordination
pass on shared sections. Our monthly horizon already uses rolling-horizon decomposition for
the same reason. Here are our solve times by instance size.

**"What if the optimizer is wrong?"** → Then the planner overrides it, and we record the
override with a reason. Those overrides are training data, and closing that loop is the
deployment plan.

**"How long did the solve take?"** → Say the real number and the optimality gap. Never say
"instantly."

**Explain line 40 of this file.** → Rule 2 of doc 9. This is why you never merge code you
cannot explain.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Nobody can code well enough by October | High | Fatal | Week-0 bootcamp; learn narrow and late; pairing; Streamlit before React; AI assistants with rule 2 |
| 2 | Big-bang integration fails in week 12 | High | Fatal | Vertical slice rule; Wednesday integration checkpoints; `main` always runs |
| 3 | Solver too slow or infeasible on stage | Medium | Fatal | Precomputed costs; `F(t)` pruning; 10 s time limit; `unsched` slack; cached demo scenario |
| 4 | Scope creep | High | High | The cut list in doc 3; 20 Nov feature freeze; "after 20 November, if we're green" |
| 5 | Judge asks about BDMS and we have no answer | Medium | High | Doc 1, rehearsed, assigned to seat 6 |
| 6 | The ML layer is visibly decorative | Medium | High | Doc 6 — duration prediction consumed by the optimizer, plus the value experiment |
| 7 | Baseline looks rigged | Medium | High | Two baselines, B2 is the serious one; fairness rules stated on the slide; report the trade-off |
| 8 | A member drops out or goes quiet | Medium | Medium | Pairing on every seat; two people can run the demo; daily one-line status |
| 9 | Laptop, projector or network failure at the finale | Medium | High | Two laptops, USB, backup video, everything offline, printed one-pagers |
| 10 | A safety claim is wrong and a railway judge catches it | Low | High | Rulebook reviewed by a domain contact; every simplification labelled as one; never assert what you have not verified |
| 11 | The demo breaks the night before | Medium | High | The `demo` tag, updated every Sunday; freeze on 20 Nov |
| 12 | No railway contact is ever found | Medium | Medium | Start in week 1; fall back to published manuals and label all rules "derived from published sources, simplified for the prototype" |

## The three things that decide this

If everything else slips, protect these:

1. **A working CP-SAT optimizer that genuinely reduces the number of blocks.** Not a
   dashboard. The engine is the project.
2. **An honest, paired benchmark against a serious baseline**, with the trade-off stated.
3. **A team that speaks the railway's language** and can answer the BDMS question in one
   sentence.

Everything else — the map, the monthly view, the approval workflow, the polish — is upside.

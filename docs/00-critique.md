# 00 · Honest critique of our concept note

The note you uploaded is a good *framing* document. It gets the central insight right
(coordination between departments is the differentiator), picks the right solver
(OR-Tools CP-SAT), and shows real discipline about honesty — "do not claim percentage
improvements as real railway results" is exactly the right instinct and most SIH teams
get that wrong.

But it is a concept note written without domain research, and there are ten specific
things in it that will cost us marks in front of a railway officer. Each one below has a
fix. Doing these ten things is roughly the difference between a decent finalist and a
winner.

---

## 1. It does not know that the incumbent systems already exist  ← **most serious**

CRIS already runs **BDMS — the Block & Disconnection Management System** — described as a
unified platform for real-time processing and monitoring of *traffic, power and
disconnection blocks across departments*, accessed through TDMS. And since 2018 the
Railway Board has mandated a **corridor block** policy: every section keeps the track
vacant for at least three hours for maintenance, a decision taken after an IIT Bombay
study, credited with cutting rail fractures from ~2,500 to under 250.

So a judge from the Ministry opens with: *"We already have BDMS, and we already have
three-hour corridor blocks. What are you adding?"* Our note has no answer to that.

**Fix.** Reframe. BDMS is a **workflow system** — it routes a demand from the requesting
department to the sanctioning authority and tracks its status. It records decisions; it
does not *make* them. The corridor policy fixes *when* the window exists; it does not
decide *which of the 200 pending jobs go into it, together, safely*. That packing and
sequencing decision is today made by a Section Controller and departmental officers over
phone calls and spreadsheets, section by section, with no network-wide view.

**Our project is the decision layer that sits on top of BDMS-style requisition data and
COA train-running data.** Same inputs, same outputs, same human sanction — we replace the
phone calls in the middle with a solver. That is a defensible, modest, deployable claim,
and it is far stronger than "we built a dashboard."

Say it out loud in the first 30 seconds of the pitch. See [`01-positioning.md`](01-positioning.md).

## 2. The ML task as specified is circular

The note says: generate synthetic data, then train a Random Forest to predict failure
risk. But if we generate the data with a rule and then train a model to rediscover that
rule, the model has learned nothing — it has memorised our own generator. A judge who
asks "what is the model learning that your formula didn't already encode?" ends that
conversation. And the note's own excellent principle — *"do not use AI merely as a
label"* — is violated by its own proposal.

**Fix.** Change the primary ML task to **block duration and overrun prediction**. Given a
task's activity type, asset, crew, site access, season and history, predict how long the
work will *actually* take and the probability it overruns its sanctioned window. This is:

- **decision-relevant** — the prediction is the `duration` parameter the optimizer
  consumes, so the ML output literally changes the schedule;
- **honest** — block overruns are a genuine, well-known IR operational pain, because an
  overrun block cascades into train delays;
- **testable** — we can show that planning with predicted durations produces fewer
  overruns than planning with nominal durations, which is a real experimental result.

Keep asset risk scoring, but do it properly (survival/hazard framing, temporal split,
calibration curve, SHAP). Details in [`06-ml.md`](06-ml.md).

## 3. The optimizer formulation will not scale

The note proposes `X(task, time, corridor) ∈ {0,1}`. With 200 tasks × 672 fifteen-minute
slots in a week × 16 sections that is ~2.1 million booleans. CP-SAT will choke, and worse,
the formulation makes "minimise the number of separate blocks" awkward to express.

**Fix.** Make **the block the decision object, not the task.** Enumerate candidate blocks
(section × window), give each a boolean `open[b]`, and assign tasks to blocks with
`x[t,b]`. Then "minimise separate blocks" is literally `minimise Σ open[b]`, and
coordination *emerges* from the solver packing tasks into already-open blocks. Use CP-SAT
optional interval variables for within-block sequencing. Precompute train-disruption cost
per candidate block **outside** the solver so it enters as a constant. Model size drops to
a few thousand variables and it solves in seconds. Full spec in [`05-optimizer.md`](05-optimizer.md).

## 4. "Train disruption" is never defined

It appears in the objective with weight `w2` and is never given a formula. That is the
single most important number in the whole system — it is what a railway operator actually
cares about — and we cannot leave it as a vibe.

**Fix.** Define it concretely: for candidate block *b* on section *s* over `[t1,t2]`, take
every train path in the COA timetable that crosses that section-time rectangle, and cost
it as `Σ_trains priority_weight(class) × minutes_delayed_or_cancelled`, where class weights
follow IR train priority (Vande Bharat / Rajdhani > Mail-Express > Passenger/MEMU >
Freight). Computable, explainable, and it makes the time-distance chart visualisation
meaningful.

## 5. Safety compatibility is treated as optional, not as a hard rule

The note says compatible activities "may be candidates for a shared window." In a
safety-critical domain that phrasing is a red flag. Compatibility is governed by rules,
not by convenience: you cannot tamp track under live 25 kV OHE without a power block; S&T
work needs a signed disconnection notice; two gangs cannot occupy the same metres of
track.

**Fix.** Write an explicit **rulebook** — a version-controlled YAML file of activity
types, the permits each requires (traffic block / power block / disconnection), which
pairs may share a window, and minimum physical separation. Feed it to the solver as hard
constraints. Have a mentor or a railway contact review it. Showing judges a reviewed
rulebook file is worth more than any amount of UI polish.

## 6. There is no human workflow or audit trail

The note has "human approval" as one box in a diagram. But the actual deliverable in this
domain is a **sanctioned block plan with an auditable trail of who approved what and
why** — that is what makes it deployable rather than a science project.

**Fix.** Build the lifecycle: `requisition → auto-plan → planner review/edit → sanction →
block order issued → executed → returned → logged`. It mirrors BDMS, it is cheap to build
(a status column and an events table), and it is a direct answer to "how would this
actually be used?"

## 7. The map is the wrong hero visual

Every controller in India reads a **time–distance chart** (the "train graph") daily —
distance on one axis, time on the other, each train a diagonal line. Draw our proposed
blocks as rectangles on that chart and a railway judge understands our entire contribution
in three seconds, with no explanation.

**Fix.** Train graph is the hero. A schematic line-and-station diagram is the secondary
view. A Leaflet/Mapbox geographic map is a *nice-to-have* we add only if time remains — it
looks impressive to a lay audience and tells a railway person nothing they need.

## 8. There is no robustness story

One scenario showing "7 blocks became 3" proves nothing; we could have cherry-picked it.

**Fix.** Run 30+ seeded random scenarios across three demand levels, report **mean ± 95%
confidence interval** on paired per-scenario deltas, and include ablations. And
deliberately show one metric where the optimiser *trades off* (e.g. slightly more total
block-hours in exchange for far fewer separate blocks and far lower train cost).
Volunteering a trade-off you understand builds more credibility with a technical judge
than a clean sweep on every metric. Protocol in [`07-evaluation.md`](07-evaluation.md).

## 9. The single baseline is too easy to beat

Comparing against "everyone books independently" is a strawman, because current IR practice
is *already* the corridor block policy.

**Fix.** Two baselines. **B1: departmental FCFS** (models uncoordinated requisitioning —
the "before" story). **B2: corridor-policy greedy** (all work forced into the fixed daily
three-hour corridor window, packed greedily, no cross-department optimisation — models
current best practice). Beating B1 shows the problem is real. Beating **B2** is the claim
that actually matters. Most teams will not think of B2; including it is a differentiator.

## 10. The scope is too large for a team with zero coding experience

Ten workflow stages, an ML layer, an optimizer, a map, weekly and monthly views, what-if
simulation, explainable AI, and a full React/Next.js + FastAPI + PostgreSQL stack — from
a standing start, in three months, while learning to program.

**Fix.** A ruthless cut list, a two-stage UI strategy (throwaway Streamlit first, React
only after the engine works), and a "vertical slice" discipline: at every point in the
next three months there must exist an end-to-end thing that runs, even if each layer is
thin. See [`03-scope.md`](03-scope.md).

---

## One thing to actively avoid

Search results show other teams pitching **GNN-based cascading delay prediction** for this
problem statement. Do not. On synthetic data a graph neural network cannot learn anything
a 30-line event-propagation simulation doesn't give you, it will eat weeks, and it is
exactly the kind of unmotivated complexity a good technical judge probes and finds hollow.
Simulate delay propagation deterministically — it is more explainable, more defensible,
and takes an afternoon.

## What the note gets right — keep all of this

- Cross-department coordination as the core differentiator. Correct, and it is the pitch.
- OR-Tools CP-SAT, FastAPI, Python. Correct choices.
- Explainability as a first-class feature in a safety-critical domain. Correct, and doc 5
  shows how to do it with the solver itself instead of hand-written text.
- The what-if simulator. Genuinely the killer feature — it turns a report generator into a
  decision-support tool, and it demos beautifully.
- The refusal to fake access to confidential operational systems, and the insistence on
  labelling results as simulated. Keep that integrity; it reads as maturity.

## Sources

- [IRFCA — Indian Railways FAQ, Railway Operations II](https://irfca.org/faq/faq-ops2.html)
- [Deccan Herald — tracks kept vacant three hours daily for maintenance](https://www.deccanherald.com/amp/story/india%2Frailway-tracks-kept-vacant-for-few-hours-every-day-for-maintenance-ashwini-vaishnaw-3452932)
- [PIB — Measures taken by Indian Railways to improve safety in train operations](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1947081)
- [CRIS BDMS application overview](https://www.scribd.com/document/938691657/BDMS-User-Manual)
- [Indian Railways — AC Traction Manual Part I, Ch. 6 (power blocks, permit to work)](https://indianrailways.gov.in/railwayboard/uploads/codesmanual/ACTraction-II-P-I/ACTractionIIPartICh6.htm)
- [SIH 2026 problem statement catalogue](https://blinknbuild.in/Assets/SIH_2026_All_226_Problem_Statements_Master_Catalogue.pdf)

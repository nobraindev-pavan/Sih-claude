# 08 · Roadmap and roles

Today is **7 September 2026**. SIH 2026 launched 21 August; internal college hackathons run
through **September**, screening in **October**, the shortlist in **November**, and the
Grand Finale — a 36-hour software sprint — in **December 2026**. Confirm the exact dates
with your SPOC this week; everything below hangs off them.

You have roughly **two weeks** until the internal hackathon and **thirteen weeks** to the
finale. That is enough, but only with the cut list in doc 3 held firmly.

## Roles for six

SIH teams are six members with at least one female member, plus two mentors. Assign these in
week 1 and do not rotate them — with zero starting experience, depth in one area beats
shallow familiarity with all of them.

| # | Role | Owns | The one thing they must master |
|---|---|---|---|
| 1 | **Optimization lead** | `optimizer/` — the CP-SAT model | OR-Tools job-shop scheduling |
| 2 | **Data & backend** | schema, generator, connectors, FastAPI | Python data structures + pydantic |
| 3 | **ML** | duration model, risk model, the value experiment | pandas + LightGBM + calibration |
| 4 | **Frontend — visualisation** | train graph, Gantt, network diagram | SVG / Plotly in React |
| 5 | **Frontend — application** | dashboard, what-if, explanation panel, approval flow | React components + a UI kit |
| 6 | **Domain, product & pitch** | rulebook, field mapping, deck, video, demo delivery, repo hygiene | The railway domain (doc 2) |

**Seat 6 is not a consolation prize.** At SIH, the team that understands its domain and
tells a clean story beats the team with slightly better code, every time. This person reads
the manuals, gets the thirty-minute conversation with a railway officer, writes the
rulebook, runs the demo, and keeps the board. If anything, give it to your most persuasive
member.

**Pairing.** 1+2 pair on the engine (they share the data contract). 4+5 pair on the UI.
3 works alongside 1, because the duration prediction feeds the optimizer directly. 6 floats,
tests everything as a user, and is the first to notice when the demo has broken.

**Cross-training rule:** at least two people must be able to run the full demo from a clean
machine. Rehearse that, not just the presentation.

---

## Phase 0 — 7 to 14 September · Lock the idea, build the spine

The goal this week is *not* a working system. It is a locked scope, a working toy, and a
deck good enough to win a college hackathon.

- [ ] **Everyone:** read docs 0–3, and the domain primer twice. (Day 1)
- [ ] **Everyone:** Python bootcamp, 3–4 days, doc 9. Non-negotiable, including seat 6.
- [ ] Confirm internal hackathon date and submission format with the SPOC.
- [ ] Lock the project name, the one-line pitch, and the six roles.
- [ ] **Seat 6:** start the search for a railway contact *now* — it has the longest lead time.
- [ ] **Seat 2:** write `core/models.py` (the schema in doc 4) and review it as a team.
- [ ] **Seat 2:** `gen/generate_scenario.py` producing the Vijaypur division — network,
      timetable, 60 tasks. Small first; scale later.
- [ ] **Seat 1:** OR-Tools job-shop tutorial, then a notebook toy: 10 tasks, 3 sections,
      5 windows, minimise `Σ open[b]`. **This is the whole idea in 60 lines** and it must
      exist by 14 September.
- [ ] **Seat 4:** a matplotlib time–distance chart of the synthetic timetable, with block
      rectangles drawn on it. Static is fine.
- [ ] **Seat 6:** first draft of `data/rulebook.yaml`, 8–10 activity types.
- [ ] **Seat 3, 5:** finish the bootcamp, then help 2 and 4 respectively.

**Gate (14 Sept):** one notebook that shows a baseline of 7 blocks becoming 3 optimized
blocks, on one chart. If that exists, the idea is proven and everything after is engineering.

## Phase 1 — 15 to 30 September · Win the internal hackathon

Streamlit, not React. Streamlit turns Python into a web app with no frontend knowledge, and
it is the correct tool for this fortnight. You will throw it away in October and that is
fine — it is scaffolding, not waste.

- [ ] Full CP-SAT model: constraints 1–8 from doc 5, with the `unsched` slack.
- [ ] Rulebook-driven permits and compatibility, wired into the model.
- [ ] `traffic_cost.py` — the precomputed per-block train disruption.
- [ ] Baseline **B1** (departmental FCFS).
- [ ] Streamlit app: pick a scenario → run baseline → run optimizer → train graph with
      blocks overlaid → KPI comparison table.
- [ ] Model validation tests 1–6 from doc 5.
- [ ] Deck: problem, the BDMS/corridor-policy positioning (doc 1), architecture, live demo,
      metrics, roadmap.
- [ ] **Rehearse the demo five times.** Time it. Then rehearse it five more times.

**Gate (30 Sept):** internal hackathon won or nominated.

## Phase 2 — 1 to 31 October · The real system

Screening happens this month; this is also when the project stops being a prototype.

- [ ] FastAPI backend, SQLite store, clean JSON API. Seat 2.
- [ ] React + Vite frontend replacing Streamlit. Seats 4 and 5. Use a component library
      (Mantine or shadcn/ui) — do not hand-roll CSS.
- [ ] Interactive train graph: zoom, hover a train for its number and class, click a block.
- [ ] Baseline **B2** (corridor-policy greedy) — the one that matters.
- [ ] `eval/harness.py`: 30 scenarios, paired deltas, mean ± CI, one command.
- [ ] ML duration + overrun model, quantile regression, feeding the optimizer. Seat 3.
- [ ] Explanation panel: per-block cost decomposition.
- [ ] Constraints 9–12 (diversion routes, crew travel, dependencies, policy caps).
- [ ] Field-mapping document and the stubbed API connectors. Seat 6.
- [ ] Monthly view with rolling-horizon decomposition.

**Gate (31 Oct):** `python -m eval.harness --scenarios 30` produces the full comparison
table, and a teammate who did not write it can start the app from a clean clone in under
five minutes with a documented command.

## Phase 3 — 1 to 25 November · Depth, then freeze

- [ ] **What-if simulator** — add a freight path, remove a crew, inject an urgent defect,
      extend a duration → re-solve → visual diff of the two plans. Seat 5 + seat 1.
- [ ] **Counterfactual explanations** — "why not this window?" via re-solve, plus
      `SufficientAssumptionsForInfeasibility` mapped to plain English. Seat 1. *This is the
      standout feature; give it real time.*
- [ ] Risk model with calibration and SHAP; the ML value experiment notebook. Seat 3.
- [ ] Approval workflow and audit trail.
- [ ] Weight sliders in the UI.
- [ ] Ablations 1–5 and the Pareto frontier chart. Seat 3 + seat 1.
- [ ] Robustness pass: solver time limits, graceful `unsched` narration, never a crash on a
      perturbed scenario, sensible empty states.
- [ ] Full evaluation report as a PDF.
- [ ] Accessibility and polish: readable at projector resolution, high contrast, no tiny text.

**FEATURE FREEZE — 20 November.** After this date: bug fixes, rehearsal and documentation
only. Write the date on the wall now. Every team that ignores its freeze date arrives at the
finale with a half-finished feature and a broken demo.

- [ ] 25 Nov: record the **backup demo video**. Full run, narrated, screen-captured.
- [ ] 25 Nov: tag `v1.0-demo` and verify a clean clone runs it.

## Phase 4 — December · The Grand Finale

**Do not plan to build at the finale.** Arrive finished. The 36 hours are for judging rounds,
responding to feedback, and polish — not for construction. Every team that plans to build
during the sprint demos something broken.

Prepare a **feature bank**: three small, pre-designed additions you can implement live in
under two hours each, so that when a judge in round one says "could you show X?", you show
it in round two. Judges reward visible responsiveness more than any single feature.

Suggested bank: (a) a new constraint type toggle, e.g. "no night blocks on this section";
(b) an extra KPI or export to a printable block order; (c) a second scenario profile, e.g.
monsoon season with inflated durations.

**Finale kit:** two laptops with identical working setups · everything offline-capable, no
CDN and no live API · the repo on a USB stick · the backup video on both laptops and the USB
· printed one-pagers of the architecture and the metrics · chargers, HDMI adapter, extension
cord · the deck exported to PDF as well as its native format.

## Cadence

- **Monday:** 30-minute planning. What is this week's vertical slice?
- **Wednesday:** integration checkpoint. Everything merged and running. No exceptions.
- **Sunday:** demo to each other. Whoever is scheduled runs the whole system end to end.
- **Always:** `main` runs. If `main` is broken, fixing it is the only priority.
- Keep a `demo` tag that always works, updated after each Sunday demo. This is your
  insurance policy.

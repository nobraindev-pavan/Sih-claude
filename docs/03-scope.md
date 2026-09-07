# 03 · Scope — what we build and what we refuse to build

## The rule that governs every decision below

**Always keep a vertical slice that runs.** At every moment between now and December there
must exist a command that loads a scenario, produces a plan, and shows it. Each layer may
be thin. It may never be missing. A team with zero coding experience that keeps this rule
will beat a team with more experience that builds four beautiful disconnected pieces and
integrates them in the last week. Integration is where projects die.

## The spine — nine things, in dependency order

Nothing outside this list is allowed to start until everything in it exists in *some* form.

1. **Unified schema + synthetic data generator** for TMS / SMMS / TDMS / COA. Seeded and
   reproducible.
2. **Network + timetable model** — sections, kilometre chainage, train paths, the
   time–distance chart.
3. **Candidate window generation** — corridor-policy windows plus timetable gaps, per section.
4. **Safety rulebook** — YAML: activity types, required permits, compatibility pairs,
   minimum separation.
5. **CP-SAT optimizer** — blocks as decision objects. The heart. See doc 5.
6. **Two baseline schedulers** — departmental FCFS, and corridor-policy greedy. See doc 7.
7. **Benchmark harness** — N seeded scenarios, metrics table, mean ± CI.
8. **UI** — train graph with blocks overlaid, block plan list, KPI strip, explanation panel.
9. **What-if re-optimisation** — change an assumption, re-solve, diff the plan.

Then, and only then, the two depth features:

10. **ML duration/overrun model** feeding the optimizer's duration parameter (doc 6).
11. **Counterfactual explanations** — "why not Tuesday 14:00?" answered by re-solving (doc 5).

## The cut list — say no to these, on purpose

| Cut | Why | What we do instead |
|---|---|---|
| Next.js | We need no server-side rendering, no routing complexity, no build config we don't understand | **React + Vite**, single page |
| PostgreSQL (until Nov) | Zero benefit at our scale, a whole extra thing to install and break | **SQLite**, one file, checked into the repo as a fixture |
| Docker / Kafka / microservices | Nothing here needs them; they will eat a week and impress nobody | One FastAPI process, one React app |
| Geographic map (Leaflet/Mapbox) | Looks impressive to a lay audience, tells a railway person nothing the train graph doesn't | Schematic SVG line diagram; add a real map in Nov *only* if everything else is done |
| Graph neural networks | Cannot learn anything real from synthetic data; huge time sink; a good judge will find it hollow | Deterministic delay-propagation simulation, ~30 lines |
| LLM chatbot / "ask your data" | Fashionable, irrelevant, and it invites hallucination into a safety-critical demo | Structured explanation panel driven by the solver's own cost decomposition |
| Real authentication | Nobody is attacking our hackathon demo | A role dropdown: *viewing as DOM / Sr.DEN / Sr.DSTE / Sr.DEE* |
| Mobile app | Not asked for | Responsive web, which we get free |
| Real-time streaming ingestion | We have no stream | Batch load + a "refresh" button |
| Multi-division / all-India scale | Not needed to prove the idea, and it makes solve times unpredictable on stage | One realistic division, and a paragraph on how it scales |

If someone proposes something not on the spine, the answer is "after 20 November, if we're
green." Write that date on the wall.

## Prototype scale — the synthetic division

Big enough to be non-trivial, small enough to solve in seconds on a laptop. Design it once,
in week 1, and never change it — every benchmark number we ever quote must come from the
same world.

**Vijaypur Division** (fictional, realistic):

- **Main corridor:** double line, electrified, ~180 km, 12 block stations, 11 block sections.
- **Branch line:** single line, electrified, ~60 km, 5 stations, 4 block sections.
  *(The single line is deliberate: on it, any block is a total closure, which forces the
  optimizer into genuinely hard trade-offs and gives the demo a dramatic moment.)*
- **A diversionary route** connecting two points of the main corridor — so we can encode
  the network-level constraint "never block the main line and its diversion at once."
- **Timetable:** ~120 train paths/day — 6 premium (Vande Bharat / Rajdhani class), 24
  mail/express, 18 passenger/MEMU, ~70 freight paths, plus one daily 3-hour corridor block
  per section per Railway Board policy.
- **Assets:** ~2,000 — track segments at 500 m granularity, ~90 signals, ~40 point
  machines, ~35 OHE elementary sections, 12 level crossings, 4 major bridges.
- **Demand:** ~180–220 open maintenance tasks in the planning month, split roughly
  Engineering 45% / S&T 30% / TRD 25%.
- **Planning horizon:** 7 days for the weekly plan, 30 days for the monthly plan, at
  15-minute granularity.

Store the whole world as a versioned fixture (`data/scenarios/vijaypur_v1/`). Seeded
generation, committed outputs, so every team member and every benchmark run sees byte-identical
data.

## Definition of done, per phase

We are done with a phase when a teammate who did not write the code can run one command and
see the result. Not when it "works on my machine", not when it is "basically done."

- **Internal hackathon (Sept):** spine items 1–3, 5 (basic), 6 (B1 only), 8 (Streamlit),
  and one honest before/after chart.
- **Screening (Oct):** all of 1–9, React UI, FastAPI backend.
- **Finale (Dec):** everything, plus 10 and 11, plus a 30-scenario benchmark report, plus a
  rehearsed demo and a recorded backup video.

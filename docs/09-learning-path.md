# 09 · Zero to productive — the learning path

Six people with no coding experience, thirteen weeks, one hard deadline. This is
achievable, but only with an unusual discipline: **learn narrow, learn late, learn by
building the actual project.** Do not take a general programming course. You do not have
time to become programmers; you have time to become people who can build this one thing.

## The rules

1. **No tutorial that isn't immediately used.** Learn a thing on the day you need it.
2. **Never merge code you cannot explain line by line.** Judges *will* point at a line and
   ask. Before every merge, explain your file out loud to a teammate. If you can't, you
   haven't finished.
3. **Type the code.** Do not copy-paste tutorial code. Muscle memory is real and it is the
   difference between debugging in five minutes and five hours.
4. **Errors are the curriculum.** Read the last line of the traceback first, then the file
   and line number. Most of learning to program is learning to read errors calmly.
5. **Use AI assistants heavily — and interrogate them.** This is normal, expected practice
   in 2026 and no judge will hold it against you. But make it a habit to ask "explain this
   line", "what happens if this input is empty", "what's a simpler way". Rule 2 still binds.

## Week 0 bootcamp — everyone, 3–4 days, ~5 hours a day

Everyone, seat 6 included. The domain owner who cannot read the code cannot defend it.

**Day 1–2 — Python core.** Variables, types, `if`, `for`, functions, lists, dicts, list
comprehensions, reading and writing files, imports, `try/except`. Source: the official
Python tutorial sections 3–6, or *Python for Everybody* (free, Coursera/py4e.com), chapters
1–10. Skip classes for now.

**Day 3 — Tools.** VS Code, the terminal, `python -m venv`, `pip install`, and git: `clone`,
`add`, `commit`, `push`, `pull`, `branch`, `checkout`. Everyone makes one commit to this repo
on day 3. That is the day the team becomes a team.

**Day 4 — pandas.** `read_csv`, filter, `groupby`, `merge`, `to_csv`. Then one exercise:
load the synthetic tasks file, and print how many tasks each department has open per section.
That exercise is real project work, which is the point.

**Checkpoint:** every member can write a function that reads a CSV, filters rows on a
condition, and prints a summary — from scratch, without looking anything up.

## Then, by seat

### Seat 1 — Optimization

Your path is short and deep. Everything else is a distraction.

1. OR-Tools **CP-SAT primer** (the official Python guide) — 2 hours.
2. The **job-shop scheduling** example. Read it, run it, then **modify it**: add a machine,
   add a task, change the objective. Do this until it feels obvious. ~1 day.
3. The **employee scheduling** example — for optional variables and soft constraints. ~4 hours.
4. `NewOptionalIntervalVar`, `AddNoOverlap`, `AddCumulative`, `OnlyEnforceIf`. These four are
   90% of what you need. Write a one-page cheat sheet in your own words.
5. Then build the doc 5 toy and grow it.

Total: about four days to be genuinely productive. This is the highest-leverage learning in
the project.

### Seat 2 — Data & backend

1. Python classes and `pydantic` models — 3 hours. This is how the schema in doc 4 becomes code.
2. `random` and `numpy.random` with **seeding** — the generator must be reproducible.
3. FastAPI official tutorial, first user guide section only — half a day. You need `@app.get`,
   `@app.post`, response models and CORS. Nothing else.
4. SQLModel (SQLAlchemy + pydantic in one) — half a day. Or, honestly, start with CSV and
   pandas and add the database in October when it hurts.

### Seat 3 — ML

1. scikit-learn "Getting Started" + `train_test_split`, `cross_val_score`, metrics — 1 day.
2. LightGBM or XGBoost quickstart — half a day. `fit`, `predict`, `feature_importances_`.
3. **Calibration** — `sklearn.calibration.calibration_curve` and why it matters. 2 hours,
   and it is the thing that will most distinguish your work.
4. Quantile regression with LightGBM (`objective="quantile"`) — 1 hour, and it earns the P80
   argument in doc 6.
5. SHAP quickstart — 2 hours.
6. matplotlib well enough to make three clean charts.

### Seats 4 & 5 — Frontend

This is the longest ramp. Start in week 1 in parallel with the bootcamp, and **do not touch
React until October** — Streamlit carries you through the internal hackathon.

1. HTML + CSS basics — 2 days. Flexbox and grid, and stop.
2. JavaScript: `const`, arrow functions, `map`, `filter`, template literals, `fetch`,
   destructuring, `async/await`. 3 days. Skip classes and prototypes.
3. React via the official **"Learn React"** tutorial — components, props, `useState`,
   `useEffect`, lists and keys. 4 days. Skip Redux, skip routing until you need it.
4. Vite: `npm create vite@latest`. One command; that's the whole build story.
5. **Use a component library.** Mantine or shadcn/ui. Do not hand-roll CSS — you will lose a
   week to alignment and gain nothing.
6. **Seat 4 only:** SVG coordinates (`viewBox`, `<line>`, `<rect>`, `<text>`) — the train
   graph is just lines and rectangles on a scaled coordinate system, and hand-rolled SVG will
   look better and be easier to control than any charting library. About a day, and it pays
   for itself in the demo.

### Seat 6 — Domain, product, pitch

1. The week-0 bootcamp, like everyone else.
2. Doc 2 and its sources — the highest-value hours in the project.
3. YAML syntax — 20 minutes. You own the rulebook.
4. Git and markdown well enough to keep the repo and docs tidy.
5. Presentation craft: build the deck early, iterate weekly, and rehearse relentlessly.

## Learning the domain is cheaper than learning to code, and worth more

A team of six that half-learns React and half-learns the railway will be beaten by a team
that half-learns React and *fully* learns the railway. Judges from the Ministry can evaluate
domain understanding instantly and code quality only slowly. Doc 2 is a three-hour read.
Do it in week 1, and do the second read in November.

## Common failure modes for first-time teams

| Failure | What it looks like | Prevention |
|---|---|---|
| Big-bang integration | four beautiful pieces, none of them connected, in week 12 | vertical slice rule, Wednesday integration |
| Tutorial paralysis | week 6 and still "learning React" | learn late, learn narrow, build immediately |
| The one-person project | one strong member writes everything, five spectate | pairing, and rule 2 enforced at every merge |
| Silent stuck | someone blocked for four days and says nothing | daily one-line status in the group chat, no exceptions |
| Demo built the night before | it breaks on stage | the `demo` tag, updated every Sunday |
| Scope creep | "what if we added a mobile app" | the cut list in doc 3, and the 20 Nov freeze |
| Copy-paste code nobody understands | a judge points at line 40 and the room goes quiet | rule 2 |

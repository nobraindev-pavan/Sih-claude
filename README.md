# SIH26027 — AI-Powered Railway Maintenance Block Planning

Team project plan for Smart India Hackathon 2026, Problem Statement **SIH26027**
(Ministry of Railways · Software · Transportation & Logistics / Smart Automation).

> **One line:** Indian Railways already has a system to *record* block demands (CRIS **BDMS**)
> and a policy that *reserves* maintenance windows (the Railway Board **corridor block**
> policy). What it does not have is something that **decides** — that takes 200 competing
> demands from Engineering, S&T and TRD and packs them into the fewest safe, coordinated
> blocks that cost the fewest train minutes. That decision engine is our project.

## Read in this order

| # | Document | What it is |
|---|---|---|
| 0 | [`docs/00-critique.md`](docs/00-critique.md) | Honest review of our concept note — what's strong, what will sink us |
| 1 | [`docs/01-positioning.md`](docs/01-positioning.md) | The pitch, and the answer to "we already have BDMS" |
| 2 | [`docs/02-domain-primer.md`](docs/02-domain-primer.md) | Railway vocabulary we must own before writing code |
| 3 | [`docs/03-scope.md`](docs/03-scope.md) | What we build, what we deliberately cut, prototype scale |
| 4 | [`docs/04-architecture.md`](docs/04-architecture.md) | System design + the full data model |
| 5 | [`docs/05-optimizer.md`](docs/05-optimizer.md) | The CP-SAT model spec — the heart of the project |
| 6 | [`docs/06-ml.md`](docs/06-ml.md) | ML that is decision-relevant and not circular |
| 7 | [`docs/07-evaluation.md`](docs/07-evaluation.md) | Baselines and the benchmark protocol that proves we're better |
| 8 | [`docs/08-roadmap.md`](docs/08-roadmap.md) | Dated plan Sept → Dec, roles for 6 people |
| 9 | [`docs/09-learning-path.md`](docs/09-learning-path.md) | Zero coding experience → productive, per role |
| 10 | [`docs/10-demo-and-risks.md`](docs/10-demo-and-risks.md) | 7-minute demo script, judge Q&A, risk register |

## The calendar we are actually on

SIH 2026 launched 21 Aug 2026. Internal college hackathons run through **September 2026**,
screening in **October**, shortlist in **November**, Grand Finale (36-hour software sprint)
in **December 2026**. Today is **7 September 2026** — the internal hackathon is *this month*.
Confirm exact dates with your college SPOC; the roadmap in doc 8 is built around them.

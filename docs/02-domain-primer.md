# 02 · Domain primer — the vocabulary we must own

You cannot win a Ministry of Railways problem statement while sounding like you learned the
domain from the problem statement. Every member of the team should be able to explain
everything on this page without notes. It is maybe three hours of study and it is the
highest-return three hours in the whole project.

> Verify each item against a primary source before you put it on a slide — the citations at
> the bottom are the starting points. Where we are unsure, our synthetic rulebook says
> "simplified for prototype", and we say so out loud. A judge forgives a labelled
> simplification; they do not forgive a confident error.

## The physical network

- **Block section** — the stretch of line between two consecutive block stations. Only one
  train may occupy it at a time under the **Absolute Block System**. This is the atomic unit
  of our scheduling problem: a block is granted *on a block section*.
- **Block station** — a station that can control entry to a block section.
- **Single line vs double line** — on a double line the Up and Down lines are separate, so a
  block can be taken on one line while trains run on the other (**single-line working**, at
  reduced capacity). On a single line any block closes the section completely. This
  distinction is a big source of interesting behaviour in our optimizer, so our synthetic
  division deliberately contains both.
- **Kilometre post / chainage** — location is expressed as `KM 120.500`, not as a name. Our
  spatial-overlap logic works on kilometre intervals. Getting this right is what makes
  "Engineering at KM 120–125 and S&T at KM 123 overlap" computable.
- **OHE (Overhead Equipment)** — the 25 kV AC catenary on electrified sections, sectioned
  into elementary sections that can be isolated independently.

## The kinds of block

This is the distinction the whole project turns on. There are three different things that
all get loosely called "a block", they are requested from different authorities, and they
have different safety implications:

| Type | What it stops | Requested by | Needed for |
|---|---|---|---|
| **Traffic block** (line block) | All train movement on the section | Engineering / any dept, sanctioned by Operating | Track work, bridge work, anything fouling the line |
| **Power block** | Electric traction — OHE de-energised and earthed | TRD | OHE work, and any work near/above the catenary |
| **Disconnection** | A signalling asset is taken out of the interlocking | S&T, via a **disconnection notice** signed by the Station Master | Points, track circuits, signal work |

A **traffic-cum-power block** bars all traffic (not merely electric traction) while OHE work
proceeds. Work on or near live OHE requires a **Permit To Work (PTW)** issued after the
section is isolated and earthed.

**Why this matters to our model:** these are not interchangeable. Two jobs "in the same
window" are only genuinely combinable if their permit requirements are compatible and their
physical separation is safe. Our rulebook encodes that; the optimizer treats it as a hard
constraint, never a preference.

## The corridor block policy

Since 2018 the Railway Board requires that on every section the track be kept vacant for at
least **three hours** for maintenance, with the timetable constructed around it. The policy
followed an IIT Bombay study, and rail fractures are reported to have fallen from around
2,500 to under 250 after proper maintenance became possible.

A **corridor block** means no trains — passenger or freight — run during that period. The
window is *pre-planned into the working timetable*, which is why it exists at all: capacity
this valuable cannot be found ad hoc.

**Why this matters:** the corridor window is our optimizer's preferred window class, and
"corridor-policy greedy packing" is our second, serious baseline (see doc 7). Our claim is
not "we invented the window" — it is "we fill it better."

## The existing IT systems (the four named in the PS)

| System | Owner | What it holds | What we take from it |
|---|---|---|---|
| **TMS** — Track Management System | Engineering / P.Way | Track assets, inspections, defects, ultrasonic flaw detection, due dates | Engineering task backlog, asset condition |
| **SMMS** — Signal Maintenance Management System | S&T | Signalling assets, failures, preventive schedules | S&T task backlog, disconnection requirements |
| **TDMS** — Traction Distribution Management System | Electrical/TRD | OHE and traction assets, maintenance schedules | TRD task backlog, power block requirements |
| **COA** — Control Office Application (CRIS) | Operating | Live train running, the control chart / train graph, section throughput | The timetable, train paths, priorities, traffic density |

And the one the concept note missed: **BDMS — Block & Disconnection Management System**
(CRIS), a unified platform for real-time processing and monitoring of traffic, power and
disconnection blocks across departments, reached through TDMS. It is where demands are
raised and their status tracked. **This is our integration point and our sharpest talking
point** — see doc 1.

## The people

Know who our user is; "the planner" is too vague to design for.

- **Section Controller** — in the Divisional Control Office, runs train movement on a set of
  sections in real time. Grants and monitors blocks on the day.
- **Chief Controller / Divisional Operating Manager (DOM)** — sanctions the block plan.
  **This is our primary user.** The weekly/monthly plan view is built for this seat.
- **Sr. DEN / DEN** (Engineering), **Sr. DSTE** (S&T), **Sr. DEE/TRD** (Traction
  Distribution) — divisional heads who raise and prioritise their department's demands.
  These are the *secondary* users: they see their own backlog and where it landed.
- **Site-in-charge / Gang** — executes the work and returns the block. Generates our
  feedback data (actual start, actual end, work completed, overrun reason).

## Terms to use correctly in the pitch

**Integrated block** (IR's own term for combined multi-department work — use *this* phrase,
not "coordinated block", when talking to railway people) · **block requisition** · **block
sanction** · **corridor block** · **mega block** (the large Sunday suburban blocks, e.g.
Mumbai) · **rolling block** · **caution order** and **temporary speed restriction (TSR)**
(imposed after certain work, and a real downstream cost of a block) · **line clear** ·
**engineering allowance** (slack built into the working timetable) · **permit to work
(PTW)** · **disconnection notice** · **G&SR** (General & Subsidiary Rules — the operating
rulebook).

## Homework, ranked by value

1. **Talk to one real railway person for thirty minutes.** A relative, an alumnus, a mentor,
   anyone in a division office. One conversation about how blocks actually get planned is
   worth more than a week of everything else, and it gives the pitch a line no other team
   has: *"we asked a Sr. DEN, and he told us…"*. Assign this to the domain owner in week 1.
2. Read the IRFCA FAQ pages on operations and on block working — the best plain-English
   source that exists.
3. Skim the AC Traction Manual chapter on power blocks and permit to work.
4. Skim the BDMS user manual to see the exact fields a real requisition carries, and mirror
   them in our schema. Field-level compatibility with the real system is a very cheap,
   very high-credibility win.

## Sources

- [IRFCA — Railway Operations FAQ](https://irfca.org/faq/faq-ops2.html) ·
  [Block & non-block working](https://irfca.org/faq/faq-signal4_b.html)
- [Absolute Block System — G&SR Chapter VIII](https://railnet.in/sr/mdzti/content/files/Chapter-8.pdf) ·
  [Automatic Block System — Chapter IX](https://railnet.in/sr/mdzti/content/files/Chapter-9.pdf)
- [AC Traction Manual Part I, Chapter 6 — power blocks and PTW](https://indianrailways.gov.in/railwayboard/uploads/codesmanual/ACTraction-II-P-I/ACTractionIIPartICh6.htm)
- [CRIS BDMS application overview](https://www.scribd.com/document/938691657/BDMS-User-Manual)
- [PIB — safety measures in train operations](https://www.pib.gov.in/PressReleasePage.aspx?PRID=1947081)
- [Deccan Herald — three-hour daily maintenance vacancy policy](https://www.deccanherald.com/amp/story/india%2Frailway-tracks-kept-vacant-for-few-hours-every-day-for-maintenance-ashwini-vaishnaw-3452932)

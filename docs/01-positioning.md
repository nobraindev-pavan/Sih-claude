# 01 · Positioning — what we say we are

## The pitch (30 seconds, memorised, everyone can say it)

> Indian Railways keeps three hours of every section vacant every day for maintenance —
> that is Railway Board policy. Filling those three hours is still a human job: Engineering,
> Signal & Telecom and Traction Distribution each raise their own block demands, and a
> Section Controller reconciles them by phone, section by section.
>
> We built the missing decision layer. It takes the same demands BDMS already collects and
> the same train chart COA already produces, predicts which assets are actually at risk and
> how long each job will really take, and then solves for the smallest set of safe,
> coordinated blocks that clears the most critical work at the lowest cost in train minutes.
>
> Every recommendation comes with the reason it was chosen and what it would have cost to
> choose otherwise. A planner still sanctions it. We are not replacing the controller — we
> are giving them a plan worth reviewing.

## The three questions a Ministry judge will ask, and our answers

**"You know we already have BDMS?"**
Yes — BDMS is where a block demand is raised, routed and tracked, across traffic, power and
disconnection blocks. It is a workflow system: it records what people decide. It does not
decide. Our engine consumes exactly the fields a BDMS requisition already carries and
returns a proposed allocation for a human to sanction. We are designed to sit behind it,
not beside it.

**"You know there is already a corridor block policy?"**
Yes, and we assume it. The three-hour corridor window is an *input* to our optimizer, not
something we propose replacing — our default configuration treats it as the preferred
window class. The policy answers *when*. It does not answer *which of these 187 pending
jobs go in, in what order, with which gangs, without violating a disconnection rule*. That
is the question we answer, and today it is answered manually.

**"Where is your data from? You cannot have ours."**
Correct, and we did not ask for it and did not pretend to have it. We built a synthetic
division whose schema is field-compatible with TMS, SMMS, TDMS and COA, and every ingestion
path goes through a connector interface with one implementation today (CSV/JSON) and a
documented mapping for the real systems. Every number we show is labelled *simulated*. Give
us a sanitised month of real requisitions and the connector is the only thing that changes.

## Naming

Working name: **SANCHAY** — *Section-level Analytics & Coordinated Block Planning Engine*.
(*sanchay* = "to gather together", which is literally what the optimizer does to blocks.)
Use it consistently in the repo, deck and UI. If the team prefers another name, pick one in
week 1 and never change it again — consistency reads as professionalism.

## What we are NOT claiming

Write these on the wall. Every one of them is a trap that has sunk SIH teams:

- We are **not** an autonomous controller. A human sanctions every block. Say this before a
  judge has to ask.
- We are **not** claiming any real-world percentage improvement. Every figure is from our
  own simulation and is labelled as such on the slide it appears on.
- We are **not** claiming integration with live railway systems. We are claiming a
  connector-shaped ingestion layer and a documented field mapping.
- We are **not** claiming to have invented coordinated blocks. Integrated blocks are
  existing IR practice. We are claiming to *optimise* their composition at network scale.

Understating a real contribution beats overstating a fake one. In a safety-critical domain,
judges reward the team that clearly knows the limits of its own system.

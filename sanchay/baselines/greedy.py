"""A coordinated greedy scheduler.

Not one of the two reported baselines. It exists for two reasons:

  1. As an **ablation**: it coordinates departments but does not optimise, so
     the gap between it and CP-SAT isolates what the *solver* contributes as
     opposed to what mere coordination contributes. That distinction is worth
     a slide.
  2. As a **warm start** for CP-SAT. Handing the solver a good incumbent up
     front lets it spend its ten seconds improving rather than searching for
     any feasible plan at all.

Strategy: work through candidate blocks cheapest-first, and fill each with as
much compatible, due-soon work as it will legally hold.
"""

from __future__ import annotations

from ..core.models import CandidateBlock, Plan, Scenario, Task
from ..core.rulebook import Rulebook
from .common import ResourceLedger, finalise, place_in_block, shrink_to_fit


def schedule(sc: Scenario, rb: Rulebook, blocks: list[CandidateBlock],
             feasible: dict[str, list[CandidateBlock]]) -> Plan:
    ledger = ResourceLedger(sc, rb)
    feasible_ids = {tid: {b.id for b in bl} for tid, bl in feasible.items()}
    by_key: dict[tuple[str, int], list] = {}
    for b in blocks:
        by_key.setdefault((b.section_id, b.start_min), []).append(b)
    by_section: dict[str, list[Task]] = {}
    for t in sc.tasks:
        by_section.setdefault(t.section_id, []).append(t)
    for v in by_section.values():
        v.sort(key=lambda t: (-t.priority_score, t.due_min))

    # Cheap blocks first; among equals, prefer the longer window because it can
    # absorb more work for the same setup cost.
    order = sorted(blocks, key=lambda b: (b.train_cost, -b.duration_min, b.start_min))
    scheduled: set[str] = set()
    granted: list[tuple[CandidateBlock, list]] = []

    for cand in order:
        pool = [t for t in by_section.get(cand.section_id, [])
                if t.id not in scheduled and cand.id in feasible_ids.get(t.id, ())]
        if not pool:
            continue
        if not ledger.section_free(cand.section_id, cand.start_min, cand.end_min):
            continue
        placed: list[tuple[Task, int, int]] = []
        for task in pool:
            slot = place_in_block(task, cand, placed, rb, ledger)
            if slot is None:
                continue
            placed.append((task, slot[0], slot[1]))
            ledger.commit_task(task, slot[0], slot[1])
            scheduled.add(task.id)
        if placed:
            final = shrink_to_fit(cand, placed, by_key)
            ledger.commit_block(final.section_id, final.start_min, final.end_min)
            granted.append((final, placed))

    return Plan(method="greedy_coordinated",
                blocks=finalise(granted, rb, "greedy_coordinated"),
                unscheduled_task_ids=sorted(t.id for t in sc.tasks
                                            if t.id not in scheduled),
                solver_status="greedy")

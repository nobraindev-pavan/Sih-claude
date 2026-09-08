"""B2 - corridor-policy greedy packing.

**This is the baseline that matters.** It models current best practice on
Indian Railways: the Railway Board mandates a three-hour maintenance window on
every section daily, and work is packed into it by priority. Departments do
share the window - that is the point of the policy - but nobody optimises which
jobs go where, or trades a corridor slot against a cheap timetable gap.

Beating B1 shows the problem is real. Beating B2 is the actual claim, and it is
a harder one. Most teams will only build B1 and beat a strawman; say out loud
that you built this one too.
"""

from __future__ import annotations

from ..core.models import CandidateBlock, Plan, Scenario, Task
from ..core.rulebook import Rulebook
from .common import ResourceLedger, finalise, place_in_block, shrink_to_fit


def schedule(sc: Scenario, rb: Rulebook, blocks: list[CandidateBlock],
             feasible: dict[str, list[CandidateBlock]]) -> Plan:
    ledger = ResourceLedger(sc, rb)
    # Only the mandated corridor windows, longest first so a full window is
    # tried before a fragment of one.
    corridor = [b for b in blocks if b.window_source == "corridor"]
    corridor.sort(key=lambda b: (b.start_min, -b.duration_min))

    feasible_ids = {tid: {b.id for b in bl} for tid, bl in feasible.items()}
    by_key: dict[tuple[str, int], list] = {}
    for b in blocks:
        by_key.setdefault((b.section_id, b.start_min), []).append(b)
    queue: list[Task] = sorted(sc.tasks,
                               key=lambda t: (-t.priority_score, t.due_min))
    scheduled: set[str] = set()
    granted: list[tuple[CandidateBlock, list]] = []
    used_sections: set[tuple[str, int, int]] = set()

    for cand in corridor:
        key = (cand.section_id, cand.start_min, cand.end_min)
        if key in used_sections:
            continue
        if not ledger.section_free(cand.section_id, cand.start_min, cand.end_min):
            continue
        placed: list[tuple[Task, int, int]] = []
        for task in queue:
            if task.id in scheduled or task.section_id != cand.section_id:
                continue
            if cand.id not in feasible_ids.get(task.id, ()):
                continue
            slot = place_in_block(task, cand, placed, rb, ledger)
            if slot is None:
                continue
            placed.append((task, slot[0], slot[1]))
            ledger.commit_task(task, slot[0], slot[1])
            scheduled.add(task.id)
        if placed:
            final = shrink_to_fit(cand, placed, by_key)
            ledger.commit_block(final.section_id, final.start_min, final.end_min)
            used_sections.add(key)
            granted.append((final, placed))

    return Plan(method="baseline_corridor",
                blocks=finalise(granted, rb, "baseline_corridor"),
                unscheduled_task_ids=sorted(t.id for t in sc.tasks
                                            if t.id not in scheduled),
                solver_status="greedy")

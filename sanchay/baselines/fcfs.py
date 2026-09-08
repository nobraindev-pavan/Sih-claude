"""B1 - departmental first-come-first-served.

Models uncoordinated requisitioning: each department works its own backlog in
its own priority order and asks for the earliest acceptable window, with no
visibility of what the other two are asking for. Blocks are granted one per
requisition, which is why the same section can end up closed three times in a
week for work that could have shared one window.

This is the "before" story. It shows the problem is real. It is NOT the
baseline that matters - see corridor.py for that one.
"""

from __future__ import annotations

from ..core.models import CandidateBlock, Plan, Scenario
from ..core.rulebook import Rulebook
from .common import ResourceLedger, finalise, place_in_block

#: A controller will refuse a block that displaces too much traffic. Above this
#: weighted cost the request is pushed to a later window.
TRAIN_COST_CEILING = 400.0
DEPT_ORDER = ("ENG", "TRD", "SNT")


def schedule(sc: Scenario, rb: Rulebook, blocks: list[CandidateBlock],
             feasible: dict[str, list[CandidateBlock]],
             dept_order: tuple[str, ...] = DEPT_ORDER) -> Plan:
    ledger = ResourceLedger(sc, rb)
    granted: list[tuple[CandidateBlock, list]] = []
    scheduled: set[str] = set()

    for dept in dept_order:
        queue = [t for t in sc.tasks if t.dept == dept]
        # each department's own view of what matters: worst first, then soonest
        queue.sort(key=lambda t: (-t.severity_rank, t.due_min, -t.priority_score))
        for task in queue:
            # earliest acceptable window, and the shortest one that fits -
            # nobody requisitions four hours to do one hour of work
            options = sorted(feasible.get(task.id, []),
                             key=lambda b: (b.start_min, b.duration_min, b.train_cost))
            for cand in options:
                if cand.train_cost > TRAIN_COST_CEILING:
                    continue
                if not ledger.section_free(cand.section_id, cand.start_min, cand.end_min):
                    continue
                slot = place_in_block(task, cand, [], rb, ledger)
                if slot is None:
                    continue
                start, end = slot
                ledger.commit_block(cand.section_id, cand.start_min, cand.end_min)
                ledger.commit_task(task, start, end)
                granted.append((cand, [(task, start, end)]))
                scheduled.add(task.id)
                break

    return Plan(method="baseline_fcfs",
                blocks=finalise(granted, rb, "baseline_fcfs"),
                unscheduled_task_ids=sorted(t.id for t in sc.tasks
                                            if t.id not in scheduled),
                solver_status="greedy")

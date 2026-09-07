"""Scoring a plan.

Two things live here. `objective_of` re-implements the CP-SAT objective in
plain Python so that *every* method - both baselines, the greedy, the solver -
can be scored on the identical function. Without that, "the optimizer is
better" would just mean "the optimizer optimises its own objective", which is
not a result.

`evaluate` produces the KPI row that goes in the benchmark table. Headline
metrics for the pitch are `n_blocks` and `train_cost`: those two are what a
Divisional Operating Manager actually cares about.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..core.candidates import night_penalty
from ..core.models import CandidateBlock, Plan, Scenario
from ..core.rulebook import Rulebook
from ..optimizer.cpsat import Weights


@dataclass
class Metrics:
    method: str
    n_blocks: int
    n_coordinated_blocks: int
    coordination_rate: float          # share of blocks serving >1 department
    total_block_minutes: int
    train_cost: float                 # weighted train-minutes displaced
    trains_affected: int
    tasks_total: int
    tasks_scheduled: int
    completion_pct: float
    critical_completion_pct: float
    residual_overdue_risk: float      # priority mass left undone
    utilisation_pct: float            # productive work / sanctioned block time
    blocks_per_task_done: float
    objective: float
    solve_seconds: float
    solver_status: str
    gap_pct: float

    def as_row(self) -> dict:
        return asdict(self)


def objective_of(plan: Plan, sc: Scenario, rb: Rulebook,
                 weights: Weights | None = None) -> float:
    """The CP-SAT objective, evaluated on any plan. Lower is better."""
    w = weights or Weights()
    tasks = {t.id: t for t in sc.tasks}
    total = 0.0
    for b in plan.blocks:
        stand_in = CandidateBlock(b.id, b.section_id, b.start_min, b.end_min,
                                  b.window_source, b.train_cost, tuple(b.trains_affected))
        total += (w.train * b.train_cost
                  + w.setup
                  + w.downtime * b.duration_min
                  + w.night * night_penalty(stand_in, rb) / 15.0)
    horizon = sc.horizon_min
    for tid in plan.unscheduled_task_ids:
        t = tasks[tid]
        lateness = max(0.0, 1.0 - t.due_min / horizon)
        total += (w.overdue * t.priority_score * (1.0 + lateness)
                  + w.risk * t.risk_score * t.severity_rank)
    return round(total, 1)


def evaluate(plan: Plan, sc: Scenario, rb: Rulebook,
             weights: Weights | None = None) -> Metrics:
    tasks = {t.id: t for t in sc.tasks}
    done = set(plan.scheduled_task_ids)
    n_blocks = len(plan.blocks)
    block_min = sum(b.duration_min for b in plan.blocks)
    work_min = sum(tasks[tid].predicted_duration_min for tid in done)
    coordinated = sum(1 for b in plan.blocks if b.is_coordinated)
    trains = len({tn for b in plan.blocks for tn in b.trains_affected})

    critical = [t for t in sc.tasks if t.severity == "critical"]
    crit_done = sum(1 for t in critical if t.id in done)
    residual = sum(tasks[tid].priority_score for tid in plan.unscheduled_task_ids)

    return Metrics(
        method=plan.method,
        n_blocks=n_blocks,
        n_coordinated_blocks=coordinated,
        coordination_rate=round(coordinated / n_blocks * 100, 1) if n_blocks else 0.0,
        total_block_minutes=block_min,
        train_cost=round(sum(b.train_cost for b in plan.blocks), 1),
        trains_affected=trains,
        tasks_total=len(sc.tasks),
        tasks_scheduled=len(done),
        completion_pct=round(len(done) / len(sc.tasks) * 100, 1),
        critical_completion_pct=round(crit_done / len(critical) * 100, 1) if critical else 100.0,
        residual_overdue_risk=round(residual, 1),
        # Can exceed 100%: tasks far enough apart in km run in parallel inside
        # one block, which is the whole point of coordinating them.
        utilisation_pct=round(work_min / block_min * 100, 1) if block_min else 0.0,
        blocks_per_task_done=round(n_blocks / len(done), 3) if done else 0.0,
        objective=objective_of(plan, sc, rb, weights),
        solve_seconds=plan.solve_seconds,
        solver_status=plan.solver_status,
        gap_pct=round(plan.gap_pct, 1),
    )


def validate(plan: Plan, sc: Scenario, rb: Rulebook) -> list[str]:
    """Hard-constraint audit of a finished plan. Empty list means clean.

    Run this on every plan from every method in the benchmark. It is the only
    thing standing between you and a baseline that quietly cheats - or an
    optimizer bug that produces an illegal plan and a great-looking number.
    """
    problems: list[str] = []
    tasks = {t.id: t for t in sc.tasks}
    seen: set[str] = set()

    for b in plan.blocks:
        for tid in b.task_ids:
            if tid in seen:
                problems.append(f"{tid} scheduled more than once")
            seen.add(tid)
            t = tasks[tid]
            if t.section_id != b.section_id:
                problems.append(f"{tid} is on {t.section_id} but block is on {b.section_id}")
            if b.end_min > t.due_min:
                problems.append(f"{tid} scheduled past its due time")
            s, e = b.task_times.get(tid, (b.start_min, b.end_min))
            if s < b.start_min or e > b.end_min:
                problems.append(f"{tid} runs outside its block")

        codes = [tasks[tid].activity_type for tid in b.task_ids]
        ok, why = rb.block_is_legal(codes)
        if not ok:
            problems.append(f"block {b.id} is not a legal combination: {why}")
        if b.duration_min > rb.policy.max_block_duration_min:
            problems.append(f"block {b.id} exceeds the maximum block duration")

    overlap = set(seen) & set(plan.unscheduled_task_ids)
    if overlap:
        problems.append(f"{len(overlap)} task(s) both scheduled and deferred")
    missing = {t.id for t in sc.tasks} - seen - set(plan.unscheduled_task_ids)
    if missing:
        problems.append(f"{len(missing)} task(s) neither scheduled nor deferred")

    # section exclusivity, including diversionary routes
    div = {s.id: s.diversion_for for s in sc.sections if s.diversion_for}
    by_section: dict[str, list] = {}
    for b in plan.blocks:
        by_section.setdefault(b.section_id, []).append(b)
    for sid, bl in by_section.items():
        bl = sorted(bl, key=lambda b: b.start_min)
        for a, c in zip(bl, bl[1:]):
            if c.start_min < a.end_min:
                problems.append(f"blocks {a.id} and {c.id} overlap on {sid}")
    for sid, other in div.items():
        for a in by_section.get(sid, []):
            for c in by_section.get(other, []):
                if a.start_min < c.end_min and c.start_min < a.end_min:
                    problems.append(
                        f"block {a.id} on {sid} overlaps {c.id} on its diversion {other}")
    return problems

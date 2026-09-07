"""What-if: perturb an assumption, re-optimise, and diff the two plans.

This is what turns the project from a report generator into a decision-support
tool, and it is the best live moment in the demo: a judge names a disruption,
you toggle it, and the plan visibly re-forms.

Each perturbation is a small, honest change to the scenario - an extra freight
path, a gang off sick, a new critical defect, work running long - after which
the whole pipeline runs again. Nothing is patched incrementally; the plan is
recomputed, which is why the answer is trustworthy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

from ..core.candidates import build_candidate_blocks, feasible_pairs
from ..core.models import Plan, Scenario, Task, Train, TrainPath
from ..core.rulebook import Rulebook
from ..core.timeutil import at, stamp
from ..core.traffic_cost import TrafficCostModel
from .cpsat import BlockPlanner, Weights


@dataclass
class Perturbation:
    kind: str
    detail: str


@dataclass
class PlanDiff:
    perturbation: str
    blocks_before: int
    blocks_after: int
    deferred_before: int
    deferred_after: int
    train_cost_before: float
    train_cost_after: float
    blocks_removed: list[str] = field(default_factory=list)
    blocks_added: list[str] = field(default_factory=list)
    tasks_moved: list[tuple[str, str, str]] = field(default_factory=list)
    tasks_newly_deferred: list[str] = field(default_factory=list)
    tasks_newly_scheduled: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"WHAT-IF: {self.perturbation}",
                 f"  blocks        {self.blocks_before} -> {self.blocks_after}",
                 f"  deferred      {self.deferred_before} -> {self.deferred_after}",
                 f"  train cost    {self.train_cost_before:.0f} -> {self.train_cost_after:.0f}",
                 f"  {len(self.tasks_moved)} task(s) moved to a different window"]
        if self.tasks_newly_deferred:
            lines.append("  no longer fits: " + ", ".join(self.tasks_newly_deferred[:6]))
        return "\n".join(lines)


def diff(before: Plan, after: Plan, label: str) -> PlanDiff:
    b_map = {tid: b.id for b in before.blocks for tid in b.task_ids}
    a_map = {tid: b.id for b in after.blocks for tid in b.task_ids}
    moved = [(tid, b_map[tid], a_map[tid]) for tid in b_map
             if tid in a_map and a_map[tid] != b_map[tid]]
    return PlanDiff(
        perturbation=label,
        blocks_before=len(before.blocks), blocks_after=len(after.blocks),
        deferred_before=len(before.unscheduled_task_ids),
        deferred_after=len(after.unscheduled_task_ids),
        train_cost_before=sum(b.train_cost for b in before.blocks),
        train_cost_after=sum(b.train_cost for b in after.blocks),
        blocks_removed=sorted({b.id for b in before.blocks} - {b.id for b in after.blocks}),
        blocks_added=sorted({b.id for b in after.blocks} - {b.id for b in before.blocks}),
        tasks_moved=sorted(moved),
        tasks_newly_deferred=sorted(set(after.unscheduled_task_ids)
                                    - set(before.unscheduled_task_ids)),
        tasks_newly_scheduled=sorted(set(before.unscheduled_task_ids)
                                     - set(after.unscheduled_task_ids)),
    )


# --------------------------------------------------------------------------
# Perturbations
# --------------------------------------------------------------------------

def add_freight(sc: Scenario, n: int = 8, seed: int = 7,
                route: str = "MAIN") -> tuple[Scenario, Perturbation]:
    """Extra freight paths, of the kind a coal or steel rake demand produces.

    Deliberately routed *through* the corridor window, because that is the real
    operational tension: extra traffic is exactly what erodes the maintenance
    window the whole policy depends on.
    """
    rng = random.Random(seed)
    prefix = "BRCH" if route == "BRANCH" else "MAIN"
    secs = sorted([s for s in sc.sections if s.id.startswith(prefix)],
                  key=lambda s: s.km_from)
    trains = list(sc.trains)
    paths = list(sc.paths)
    for i in range(n):
        num = f"9{i:04d}"
        direction = rng.choice(["UP", "DN"])
        trains.append(Train(num, "FRT", direction))
        day = rng.randrange(0, sc.horizon_days)
        t = at(day, 10) + rng.randrange(0, 120, 15)   # into the corridor window
        for sec in (secs if direction == "DN" else list(reversed(secs))):
            run = int(sec.length_km / 36.0 * 60)
            paths.append(TrainPath(num, sec.id, t, t + run))
            t += run + rng.choice([2, 4, 6])
    return (replace(sc, trains=trains, paths=paths),
            Perturbation("add_freight", f"{n} extra freight paths through the "
                                        f"corridor window on {route}"))


def remove_crew(sc: Scenario, crew_type: str = "signal_team",
                n: int = 1) -> tuple[Scenario, Perturbation]:
    """A gang unavailable - sick, or diverted to a failure elsewhere."""
    crews = list(sc.crews)
    removed = []
    for c in list(crews):
        if c.crew_type == crew_type and len(removed) < n:
            crews.remove(c)
            removed.append(c.id)
    return (replace(sc, crews=crews),
            Perturbation("remove_crew", f"{crew_type} unavailable: {', '.join(removed)}"))


def urgent_defect(sc: Scenario, rb: Rulebook, section_id: str | None = None,
                  activity: str = "ENG_RAIL_RENEWAL", due_day: int = 2
                  ) -> tuple[Scenario, Perturbation]:
    """A new critical defect reported today - the commonest real disruption."""
    section_id = section_id or sc.sections[0].id
    sec = sc.section(section_id)
    act = rb[activity]
    km = round((sec.km_from + sec.km_to) / 2, 2)
    task = Task(
        id="URG-001", dept=act.dept, activity_type=activity, asset_id="URGENT",
        section_id=section_id, km_from=km, km_to=km + 0.5, severity="critical",
        raised_min=0, due_min=at(due_day, 0),
        nominal_duration_min=act.nominal_duration_min, crew_type=act.crew_type,
        risk_score=0.95, priority_score=25.0)
    return (replace(sc, tasks=sorted(sc.tasks + [task], key=lambda t: t.id)),
            Perturbation("urgent_defect",
                         f"critical {act.name} on {section_id} at KM {km}, "
                         f"due {stamp(task.due_min)}"))


def inflate_durations(sc: Scenario, factor: float = 1.25
                      ) -> tuple[Scenario, Perturbation]:
    """Work running long - monsoon conditions, or a conservative planning stance.

    This is also how you demonstrate the value of the duration model: set the
    factor to what the ML predicts instead of guessing it.
    """
    tasks = []
    for t in sc.tasks:
        new = replace(t)
        new.predicted_duration_min = int(round(t.predicted_duration_min * factor / 15) * 15)
        tasks.append(new)
    return (replace(sc, tasks=tasks),
            Perturbation("inflate_durations", f"all durations x{factor:g}"))


# --------------------------------------------------------------------------

def replan(sc: Scenario, rb: Rulebook, weights: Weights | None = None,
           hint: Plan | None = None, anchor: Plan | None = None,
           max_seconds: float = 10.0) -> Plan:
    """Run the whole pipeline on a (possibly perturbed) scenario.

    `hint` warm-starts the search; `anchor` additionally makes the objective
    prefer keeping tasks in the windows they were already sanctioned in. Pass
    the previous plan as both for a what-if: you want the smallest change that
    absorbs the disruption, not a different optimum.
    """
    from ..baselines import greedy
    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    blocks = build_candidate_blocks(sc, tc, rb)
    feasible = feasible_pairs(sc.tasks, blocks)
    planner = BlockPlanner(sc, rb, blocks, feasible, weights, anchor=anchor)
    planner.build()
    # Always warm-start. Without an incumbent the solver spends its whole time
    # limit finding any plan at all, and the result is markedly worse.
    seed_plan = hint or greedy.schedule(sc, rb, blocks, feasible)
    try:
        planner.add_hint(seed_plan)
    except Exception:
        pass
    return planner.solve(max_seconds=max_seconds)

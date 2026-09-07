"""Why this block, and why not that one.

Two layers, both driven by the model rather than by generated prose - which
matters in a safety-critical domain, where an explanation that sounds plausible
but is not derived from the actual decision is worse than none.

  `explain_block`    decomposes a chosen block into the objective terms that
                     paid for it, and lists the concrete facts behind each.

  `counterfactual`   answers "why not Tuesday 14:00?" by forcing that choice
                     and re-solving. Either it comes back with a number - this
                     alternative costs 340 more weighted train-minutes and opens
                     a fourth block - or it comes back infeasible, and we name
                     the constraint that forbids it.

The counterfactual is the single most persuasive thing in the demo. It answers
the planner's real question with a quantity instead of an assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.candidates import km_conflict, night_penalty
from ..core.models import Block, CandidateBlock, Plan, Scenario
from ..core.rulebook import Rulebook
from ..core.timeutil import overlaps, stamp
from ..core.traffic_cost import TrafficCostModel
from .cpsat import BlockPlanner, Weights


@dataclass
class BlockExplanation:
    block_id: str
    headline: str
    costs: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(sum(self.costs.values()), 1)


def explain_block(block: Block, sc: Scenario, rb: Rulebook, tc: TrafficCostModel,
                  weights: Weights | None = None) -> BlockExplanation:
    w = weights or Weights()
    tasks = {t.id: t for t in sc.tasks}
    members = [tasks[tid] for tid in block.task_ids]
    stand_in = CandidateBlock(block.id, block.section_id, block.start_min,
                              block.end_min, block.window_source, block.train_cost,
                              tuple(block.trains_affected))
    night = night_penalty(stand_in, rb)

    costs = {
        "train disruption": round(w.train * block.train_cost, 1),
        "opening a block": float(w.setup),
        "line occupancy": float(w.downtime * block.duration_min),
        "night working": round(w.night * night / 15.0, 1),
    }

    depts = sorted({t.dept for t in members})
    reasons: list[str] = []
    if block.window_source == "corridor":
        reasons.append("Falls inside the mandated three-hour corridor window, "
                       "which the working timetable already keeps clear.")
    elif block.train_cost == 0:
        reasons.append("Sits in a natural gap in the timetable - no train path "
                       "crosses this section during the window.")
    else:
        by_class = tc.breakdown(block.section_id, block.start_min, block.end_min)
        detail = ", ".join(f"{n} {cls}" for cls, n in by_class.items())
        reasons.append(f"Displaces traffic: {detail}. Weighted cost "
                       f"{block.train_cost:.0f} train-minutes.")
    if len(depts) > 1:
        reasons.append(f"Coordinates {' + '.join(depts)} in one window instead of "
                       f"{len(depts)} separate disruptions.")
    if block.permits:
        reasons.append("Permits held: " + ", ".join(sorted(block.permits)).replace("_", " ") + ".")

    urgent = sorted(members, key=lambda t: t.due_min)[:2]
    for t in urgent:
        reasons.append(f"{t.id} ({rb[t.activity_type].name}, {t.severity}) is due "
                       f"{stamp(t.due_min)}.")
    slack = block.duration_min - sum(t.predicted_duration_min for t in members)
    if slack < 0:
        reasons.append(f"Worksites are far enough apart in km to run in parallel, "
                       f"fitting {sum(t.predicted_duration_min for t in members)} "
                       f"minutes of work into a {block.duration_min}-minute window.")

    headline = (f"{block.section_id} {stamp(block.start_min)}-"
                f"{stamp(block.end_min).split()[1]} - "
                f"{' + '.join(depts)}, {len(members)} task(s)")
    return BlockExplanation(block.id, headline, costs, reasons, list(block.task_ids))


# --------------------------------------------------------------------------
# Counterfactuals
# --------------------------------------------------------------------------

@dataclass
class Counterfactual:
    task_id: str
    alternative: str
    possible: bool
    delta_objective: float | None
    delta_blocks: int | None
    reasons: list[str]

    def sentence(self) -> str:
        """Plain English, including when the answer is embarrassing.

        A negative delta means forcing the alternative produced a *better* plan
        than the one we recommended - which happens when the search had not
        converged inside its time limit. Saying so is better than hiding it: it
        is exactly what the reported optimality gap means, and a planner who
        catches the system glossing over it will not trust the rest.
        """
        if not self.possible:
            return (f"{self.task_id} cannot go in that window: "
                    + " ".join(self.reasons))
        d = self.delta_objective or 0.0
        if d > 1.0:
            bits = [f"that window is possible but costs {d:+.0f} on the objective"]
            if self.delta_blocks:
                bits.append(f"and changes the plan by {self.delta_blocks:+d} block(s)")
            return f"{self.task_id}: " + ", ".join(bits) + "."
        if d < -1.0:
            return (f"{self.task_id}: forcing that window found a plan {-d:.0f} "
                    f"BETTER than the one recommended. Our plan was not proven "
                    f"optimal within the time limit, so the search had simply not "
                    f"found this. Re-solve for longer to close the gap.")
        return (f"{self.task_id}: that window is equally good - the two placements "
                f"cost the same, so either is defensible.")


def _static_objections(task, alt: CandidateBlock, plan: Plan, sc: Scenario,
                       rb: Rulebook) -> list[str]:
    """Reasons this assignment is impossible that need no solver at all.

    Checking these first means the common cases get an instant, specific answer
    rather than a ten-second re-solve that ends in 'infeasible'.
    """
    out: list[str] = []
    if alt.section_id != task.section_id:
        out.append(f"the work is on {task.section_id}, not {alt.section_id}.")
    if alt.duration_min < task.predicted_duration_min:
        out.append(f"the window is {alt.duration_min} minutes and the work needs "
                   f"{task.predicted_duration_min}.")
    if alt.end_min > task.due_min:
        out.append(f"it ends {stamp(alt.end_min)}, after the {stamp(task.due_min)} deadline.")

    tasks = {t.id: t for t in sc.tasks}
    for b in plan.blocks:
        if b.id == alt.id:
            for other_id in b.task_ids:
                other = tasks[other_id]
                ok, why = rb.can_share_block(task.activity_type, other.activity_type)
                if not ok:
                    out.append(f"{other_id} is already in that window and {why}.")
        elif b.section_id == alt.section_id and overlaps(
                alt.start_min, alt.end_min, b.start_min, b.end_min):
            out.append(f"{b.section_id} is already blocked {stamp(b.start_min)}-"
                       f"{stamp(b.end_min).split()[1]} for {', '.join(b.task_ids[:3])}.")
    return out


def counterfactual(planner: BlockPlanner, task_id: str, alt_block_id: str,
                   base_plan: Plan, sc: Scenario, rb: Rulebook,
                   max_seconds: float = 10.0) -> Counterfactual:
    """Force `task_id` into `alt_block_id`, re-solve, and report the difference."""
    task = {t.id: t for t in sc.tasks}[task_id]
    alt = next((b for b in planner.blocks if b.id == alt_block_id), None)
    if alt is None:
        alt = next((b for b in planner.feasible.get(task_id, []) if b.id == alt_block_id), None)
    if alt is None:
        return Counterfactual(task_id, alt_block_id, False, None, None,
                              ["that window is not among the candidate blocks."])

    objections = _static_objections(task, alt, base_plan, sc, rb)
    key = (task_id, alt_block_id)
    if key not in planner.x:
        return Counterfactual(task_id, alt_block_id, False, None, None,
                              objections or ["the window fails a feasibility check "
                                             "on section, duration or deadline."])

    scratch = BlockPlanner(sc, rb, planner.blocks, planner.feasible, planner.weights)
    model = scratch.build()
    model.Add(scratch.x[key] == 1)
    scratch.add_hint(base_plan)
    try:
        alt_plan = scratch.solve(max_seconds=max_seconds)
    except RuntimeError:
        return Counterfactual(task_id, alt_block_id, False, None, None,
                              objections or ["no legal plan exists with that assignment."])

    from ..eval.metrics import objective_of
    base_obj = objective_of(base_plan, sc, rb, planner.weights)
    alt_obj = objective_of(alt_plan, sc, rb, planner.weights)
    reasons = []
    if alt.train_cost > 0:
        reasons.append(f"it displaces {len(alt.trains_affected)} train(s) "
                       f"({alt.train_cost:.0f} weighted train-minutes)")
    if alt.window_source != "corridor":
        reasons.append("it is outside the mandated corridor window")
    return Counterfactual(
        task_id, alt_block_id, True,
        round(alt_obj - base_obj, 1),
        len(alt_plan.blocks) - len(base_plan.blocks),
        reasons or ["it is simply a more expensive placement"])


def alternatives_for(planner: BlockPlanner, task_id: str, base_plan: Plan,
                     limit: int = 5) -> list[CandidateBlock]:
    """The windows a planner is most likely to ask about for this task."""
    chosen = next((b.id for b in base_plan.blocks if task_id in b.task_ids), None)
    opts = [b for b in planner.feasible.get(task_id, []) if b.id != chosen]
    opts.sort(key=lambda b: (b.train_cost, b.start_min))
    return opts[:limit]

"""The CP-SAT block planner. This is the project.

The modelling decision that matters (docs/05-optimizer.md): **the block is the
decision object, not the task.** We enumerate candidate blocks, give each an
`open[b]` boolean, and assign tasks into them. Three things follow:

  * "minimise the number of separate disruptions" is literally `sum(open[b])`;
  * coordination is *emergent* - nobody writes a rule saying "combine
    departments"; the solver combines them because opening a second block costs
    more than packing into the first;
  * the model is a bin-packing-with-setup-cost, a structure CP-SAT is good at.

The `unsched[t]` slack is a demo-safety feature, not a modelling nicety. With
it the model can never return INFEASIBLE, so a judge who perturbs the what-if
panel gets a plan with four deferred jobs and an explanation, rather than a red
error on a projector.

That is necessary but not sufficient. A model that *has* a solution can still
return UNKNOWN if the time limit expires before the solver finds one - which on
a projector looks exactly as bad as INFEASIBLE. So `solve()` also keeps the
warm-start plan and returns it on UNKNOWN. Between the two, a plan always comes
back: at worst the greedy one we started from, clearly labelled.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from ..core.candidates import km_conflict, night_penalty
from ..core.models import Block, CandidateBlock, Plan, Scenario, Task
from ..core.rulebook import ALL_PERMITS, Rulebook

#: Travel and setting-up time a crew needs around a job. Keeps a gang from
#: being in two places at once, without a full travel-time model.
MOBILISE_MIN = 20
#: Objective costs are integers in CP-SAT, so float train costs are scaled.
COST_SCALE = 10


@dataclass
class Weights:
    """Objective weights. All six are meant to be exposed as UI sliders -
    letting a judge move `setup` and watch blocks merge while train cost rises
    is one of the best twenty seconds in the demo."""
    train: int = 1
    setup: int = 500        # the coordination driver
    downtime: int = 2
    overdue: int = 50
    risk: int = 200
    night: int = 20
    #: Cost of moving a task out of the window it was already sanctioned in.
    #: Only applies when re-planning against an anchor (the what-if flow). A
    #: planner who has circulated a block plan does not want it reshuffled
    #: wholesale because one freight path was added - they want to see the
    #: smallest change that absorbs the disruption.
    stability: int = 120

    def as_dict(self) -> dict[str, float]:
        return dict(train=self.train, setup=self.setup, downtime=self.downtime,
                    overdue=self.overdue, risk=self.risk, night=self.night,
                    stability=self.stability)


@dataclass
class SolveStats:
    n_blocks: int = 0
    n_pairs: int = 0
    n_bools: int = 0
    n_separation_constraints: int = 0
    build_seconds: float = 0.0
    solve_seconds: float = 0.0
    status: str = ""
    objective: float = 0.0
    bound: float = 0.0
    notes: list[str] = field(default_factory=list)


class BlockPlanner:
    def __init__(self, sc: Scenario, rb: Rulebook,
                 blocks: list[CandidateBlock],
                 feasible: dict[str, list[CandidateBlock]],
                 weights: Weights | None = None,
                 anchor: Plan | None = None) -> None:
        self.anchor = anchor
        self.sc = sc
        self.rb = rb
        self.weights = weights or Weights()
        self.tasks = {t.id: t for t in sc.tasks}
        # Only keep blocks that at least one task could actually use.
        used_ids = {b.id for blist in feasible.values() for b in blist}
        self.blocks = [b for b in blocks if b.id in used_ids]
        self.block_by_id = {b.id: b for b in self.blocks}
        self.feasible = {tid: [b for b in bl if b.id in self.block_by_id]
                         for tid, bl in feasible.items()}
        self.stats = SolveStats(n_blocks=len(self.blocks))

    # -- model ------------------------------------------------------------
    def build(self) -> cp_model.CpModel:
        t0 = time.time()
        m = cp_model.CpModel()
        w = self.weights
        rb = self.rb

        tasks_of: dict[str, list[Task]] = {b.id: [] for b in self.blocks}
        for tid, blist in self.feasible.items():
            for b in blist:
                tasks_of[b.id].append(self.tasks[tid])

        self.open_ = {b.id: m.NewBoolVar(f"open_{b.id}") for b in self.blocks}
        self.x: dict[tuple[str, str], cp_model.IntVar] = {}
        self.unsched = {t.id: m.NewBoolVar(f"unsched_{t.id}") for t in self.sc.tasks}
        task_itv: dict[tuple[str, str], cp_model.IntervalVar] = {}
        crew_itv: dict[str, list] = {}
        self.start: dict[tuple[str, str], cp_model.IntVar] = {}

        for t in self.sc.tasks:
            for b in self.feasible[t.id]:
                key = (t.id, b.id)
                lit = m.NewBoolVar(f"x_{t.id}_{b.id}")
                self.x[key] = lit
                dur = t.predicted_duration_min
                s = m.NewIntVar(b.start_min, b.end_min - dur, f"s_{t.id}_{b.id}")
                self.start[key] = s
                task_itv[key] = m.NewOptionalIntervalVar(
                    s, dur, s + dur, lit, f"i_{t.id}_{b.id}")
                # crew occupancy runs past the work by the mobilisation time
                crew_itv.setdefault(t.crew_type, []).append(
                    m.NewOptionalIntervalVar(s, dur + MOBILISE_MIN, s + dur + MOBILISE_MIN,
                                             lit, f"c_{t.id}_{b.id}"))

        # 1. every task is scheduled exactly once, or explicitly deferred.
        #    This is what makes the model incapable of being INFEASIBLE.
        for t in self.sc.tasks:
            m.Add(sum(self.x[(t.id, b.id)] for b in self.feasible[t.id])
                  + self.unsched[t.id] == 1)

        # 2/3. a task needs an open block; an empty block is not open
        for b in self.blocks:
            members = [self.x[(t.id, b.id)] for t in tasks_of[b.id]]
            for lit in members:
                m.Add(lit <= self.open_[b.id])
            if members:
                m.Add(self.open_[b.id] <= sum(members))
            else:
                m.Add(self.open_[b.id] == 0)

        # 4. permits. A block holds the union of its tasks' requirements, and
        #    no task may work under a permit its activity forbids.
        permit_held: dict[tuple[str, str], cp_model.IntVar] = {}
        for b in self.blocks:
            for p in ALL_PERMITS:
                needers = [self.x[(t.id, b.id)] for t in tasks_of[b.id]
                           if p in rb[t.activity_type].requires]
                held = m.NewBoolVar(f"perm_{b.id}_{p}")
                permit_held[(b.id, p)] = held
                if needers:
                    for lit in needers:
                        m.Add(held >= lit)
                    m.Add(held <= sum(needers))
                else:
                    m.Add(held == 0)
                for t in tasks_of[b.id]:
                    if p in rb[t.activity_type].forbids:
                        m.Add(self.x[(t.id, b.id)] + held <= 1)
        self.permit_held = permit_held

        # 5. explicitly incompatible activities, and physical separation.
        #    Separation only bites when two gangs are on site at the same
        #    moment, so it constrains time, not membership.
        n_sep = 0
        for b in self.blocks:
            members = tasks_of[b.id]
            for i, ta in enumerate(members):
                for tb in members[i + 1:]:
                    if rb.pair_incompatible(ta.activity_type, tb.activity_type):
                        m.Add(self.x[(ta.id, b.id)] + self.x[(tb.id, b.id)] <= 1)
                    elif km_conflict(ta, tb, rb):
                        m.AddNoOverlap([task_itv[(ta.id, b.id)], task_itv[(tb.id, b.id)]])
                        n_sep += 1
        self.stats.n_separation_constraints = n_sep

        # 6. one block at a time per section, and never a section together
        #    with its diversionary route.
        block_itv = {b.id: m.NewOptionalIntervalVar(
            b.start_min, b.duration_min, b.end_min, self.open_[b.id], f"blk_{b.id}")
            for b in self.blocks}
        by_section: dict[str, list] = {}
        for b in self.blocks:
            by_section.setdefault(b.section_id, []).append(block_itv[b.id])
        for ivs in by_section.values():
            if len(ivs) > 1:
                m.AddNoOverlap(ivs)
        for sec in self.sc.sections:
            if sec.diversion_for:
                pair = by_section.get(sec.id, []) + by_section.get(sec.diversion_for, [])
                if len(pair) > 1:
                    m.AddNoOverlap(pair)

        # 7. crew capacity: you only have so many gangs of each type
        counts: dict[str, int] = {}
        for c in self.sc.crews:
            counts[c.crew_type] = counts.get(c.crew_type, 0) + 1
        for ctype, ivs in crew_itv.items():
            # Default 0, not 1. A crew type with no gangs left must make its
            # work impossible, not quietly grant one phantom gang - which is
            # exactly what a "what if this team is unavailable?" question asks.
            cap = counts.get(ctype, 0)
            m.AddCumulative(ivs, [1] * len(ivs), cap)

        # -- objective ----------------------------------------------------
        terms = []
        for b in self.blocks:
            unit = (w.train * int(round(b.train_cost * COST_SCALE))
                    + w.setup * COST_SCALE
                    + w.downtime * b.duration_min * COST_SCALE
                    + w.night * night_penalty(b, rb) * COST_SCALE // 15)
            terms.append(unit * self.open_[b.id])
        if self.anchor is not None:
            # keep the plan recognisable: every task that leaves the window it
            # was sanctioned in costs something
            anchored = {tid: b.id for b in self.anchor.blocks for tid in b.task_ids}
            for tid, bid in anchored.items():
                key = (tid, bid)
                if key in self.x:
                    terms.append(w.stability * COST_SCALE * (1 - self.x[key]))
        horizon = self.sc.horizon_min
        for t in self.sc.tasks:
            lateness = max(0.0, 1.0 - t.due_min / horizon)
            pen = (w.overdue * t.priority_score * (1.0 + lateness)
                   + w.risk * t.risk_score * t.severity_rank)
            terms.append(int(round(pen * COST_SCALE)) * self.unsched[t.id])
        m.Minimize(sum(terms))

        self.stats.n_pairs = len(self.x)
        self.stats.n_bools = len(self.x) + len(self.open_) + len(self.unsched)
        self.stats.build_seconds = round(time.time() - t0, 3)
        self._model = m
        self._task_itv = task_itv
        return m

    # -- warm start -------------------------------------------------------
    def add_hint(self, plan: Plan) -> int:
        """Seed the solver with an existing feasible plan.

        CP-SAT spends its time limit improving a good incumbent rather than
        hunting for any feasible plan, which is most of the difference between
        a usable ten-second answer and a poor one. Hints are advisory: an
        unusable hint costs nothing but is silently ignored.
        """
        if not hasattr(self, "_model"):
            self.build()
        m = self._model
        hinted_open = {b.id for b in plan.blocks if b.id in self.open_}
        n = 0
        for bid, var in self.open_.items():
            m.AddHint(var, 1 if bid in hinted_open else 0)
            n += 1
        assigned: dict[str, str] = {}
        for b in plan.blocks:
            for tid in b.task_ids:
                assigned[tid] = b.id
        for (tid, bid), var in self.x.items():
            m.AddHint(var, 1 if assigned.get(tid) == bid else 0)
            n += 1
        for tid, var in self.unsched.items():
            m.AddHint(var, 0 if tid in assigned else 1)
            n += 1
        for b in plan.blocks:
            for tid, (s, _e) in b.task_times.items():
                key = (tid, b.id)
                if key in self.start:
                    m.AddHint(self.start[key], s)
                    n += 1
        self._hint_plan = plan
        self.stats.notes.append(f"warm start from {plan.method} ({len(plan.blocks)} blocks)")
        return n

    # -- solve ------------------------------------------------------------
    def solve(self, max_seconds: float = 10.0, workers: int = 8,
              log: bool = False, seed: int = 0) -> Plan:
        if not hasattr(self, "_model"):
            self.build()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_seconds
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed
        solver.parameters.log_search_progress = log
        t0 = time.time()
        status = solver.Solve(self._model)
        elapsed = time.time() - t0

        self.stats.solve_seconds = round(elapsed, 3)
        self.stats.status = solver.StatusName(status)

        if status == cp_model.UNKNOWN:
            # Not infeasible - the time limit simply expired before the search
            # found anything. Fall back to the plan we warm-started from, which
            # is feasible by construction. A short budget then degrades to a
            # worse plan rather than to no plan.
            hint = getattr(self, "_hint_plan", None)
            if hint is None:
                raise RuntimeError(
                    f"solver returned UNKNOWN after {elapsed:.1f}s with no warm "
                    "start to fall back on - raise the time limit, or call "
                    "add_hint() before solve()")
            from ..eval.metrics import objective_of
            fallback = Plan(
                method="optimizer", blocks=list(hint.blocks),
                unscheduled_task_ids=list(hint.unscheduled_task_ids),
                solver_status=f"UNKNOWN (fell back to {hint.method})",
                # No bound was proven, so the honest gap is 100% - not the 0%
                # that leaving both at zero would report. A fallback plan that
                # claims proven optimality is worse than one that admits it has
                # no guarantee at all.
                objective_value=objective_of(hint, self.sc, self.rb, self.weights),
                best_bound=0.0,
                solve_seconds=self.stats.solve_seconds,
                weights=self.weights.as_dict())
            self.stats.notes.append(
                f"time limit expired before any solution; returned the "
                f"{hint.method} warm start")
            return fallback

        if status != cp_model.OPTIMAL and status != cp_model.FEASIBLE:
            # Genuinely unreachable: the unsched slack makes every instance
            # satisfiable. If this fires, a hard constraint is wrong.
            raise RuntimeError(
                f"solver returned {solver.StatusName(status)} - a hard constraint "
                "is over-tight; the unsched slack should make this impossible")
        self.stats.objective = solver.ObjectiveValue() / COST_SCALE
        self.stats.bound = solver.BestObjectiveBound() / COST_SCALE

        blocks: list[Block] = []
        for b in self.blocks:
            if not solver.Value(self.open_[b.id]):
                continue
            tids, times = [], {}
            for t in self.sc.tasks:
                key = (t.id, b.id)
                if key in self.x and solver.Value(self.x[key]):
                    tids.append(t.id)
                    s = solver.Value(self.start[key])
                    times[t.id] = (s, s + t.predicted_duration_min)
            if not tids:
                continue
            permits = frozenset(p for p in ALL_PERMITS
                                if solver.Value(self.permit_held[(b.id, p)]))
            blocks.append(Block(
                id=b.id, section_id=b.section_id, start_min=b.start_min,
                end_min=b.end_min, permits=permits, task_ids=sorted(tids),
                trains_affected=list(b.trains_affected), train_cost=b.train_cost,
                window_source=b.window_source, task_times=times))
        blocks.sort(key=lambda b: (b.start_min, b.section_id))
        unsched = sorted(t.id for t in self.sc.tasks if solver.Value(self.unsched[t.id]))

        return Plan(method="optimizer", blocks=blocks, unscheduled_task_ids=unsched,
                    solver_status=self.stats.status,
                    objective_value=self.stats.objective, best_bound=self.stats.bound,
                    solve_seconds=self.stats.solve_seconds,
                    weights=self.weights.as_dict())

"""The planning service: everything the API needs, with no HTTP in it.

Keeping this separate from `main.py` means the CLI, the tests and the API all
drive the same object, and none of the interesting logic is trapped behind a
web framework.

Solved scenarios are cached by (seed, demand, days, ml). Building a scenario
and its candidate blocks takes about a second and solving takes ten, so a UI
that re-solved on every click would be unusable - and a demo that pauses for
ten seconds when a judge clicks a block is a demo that has gone wrong.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from ..baselines import corridor, fcfs, greedy
from ..core.candidates import build_candidate_blocks, feasible_pairs
from ..core.models import Plan, Scenario
from ..core.rulebook import Rulebook
from ..core.timeutil import MINUTES_PER_DAY, hhmm, stamp
from ..core.traffic_cost import TrafficCostModel
from ..eval.metrics import evaluate, validate
from ..gen.generate import GenConfig, generate
from ..optimizer import whatif
from ..optimizer.cpsat import BlockPlanner, Weights
from ..optimizer.explain import alternatives_for, counterfactual, explain_block

METHOD_LABEL = {
    "baseline_fcfs": "B1 · uncoordinated requisitions",
    "baseline_corridor": "B2 · corridor policy only",
    "greedy_coordinated": "greedy coordination",
    "optimizer": "SANCHAY optimizer",
}


@dataclass
class Session:
    """One solved world, held in memory."""
    key: str
    scenario: Scenario
    rulebook: Rulebook
    traffic: TrafficCostModel
    blocks: list
    feasible: dict
    planner: BlockPlanner
    plans: dict[str, Plan]
    weights: Weights
    #: The budget the base plan was solved with. Every derived solve - a
    #: counterfactual, a what-if - must use the SAME budget, or the difference
    #: reported is partly the extra search time rather than the change being
    #: asked about. This is the easiest way to accidentally lie with this tool.
    time_limit: float = 12.0
    ml_note: str = ""
    created: float = field(default_factory=time.time)


class PlanningService:
    def __init__(self, max_sessions: int = 8) -> None:
        self.rulebook = Rulebook.load()
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        #: One lock per scenario key. The UI asks for the scenario, the plan and
        #: the comparison in parallel, all for the same world - without this the
        #: three requests each start their own solve, compete for CPU, and a
        #: badly under-converged plan wins the cache. That looked like the
        #: optimizer being bad; it was three of them fighting.
        self._building: dict[str, threading.Lock] = {}
        self._max = max_sessions
        self._model = None

    # -- building ---------------------------------------------------------
    def _duration_model(self):
        if self._model is None:
            from ..ml.duration import train_and_report
            self._model, self._model_report = train_and_report()
        return self._model

    def key_for(self, seed: int, demand: str, days: int, ml: bool,
                weights: Weights) -> str:
        w = "-".join(str(v) for v in weights.as_dict().values())
        return f"{seed}:{demand}:{days}:{int(ml)}:{w}"

    def solve(self, seed: int = 1, demand: str = "normal", days: int = 7,
              ml: bool = False, weights: Weights | None = None,
              time_limit: float = 12.0) -> Session:
        weights = weights or Weights()
        key = self.key_for(seed, demand, days, ml, weights)
        with self._lock:
            if key in self._sessions:
                return self._sessions[key]
            build_lock = self._building.setdefault(key, threading.Lock())

        with build_lock:
            # Another request may have finished this world while we waited.
            with self._lock:
                if key in self._sessions:
                    return self._sessions[key]
            return self._build(key, seed, demand, days, ml, weights, time_limit)

    def _build(self, key: str, seed: int, demand: str, days: int, ml: bool,
               weights: Weights, time_limit: float) -> Session:
        rb = self.rulebook
        sc = generate(GenConfig(seed=seed, demand=demand, horizon_days=days), rb)
        note = ""
        if ml:
            from ..ml.duration import apply_predictions
            model = self._duration_model()
            apply_predictions(sc, rb, model, quantile=True)
            note = (f"planning to the duration model's P{int(model.quantile * 100)} "
                    f"(MAE {self._model_report.mae_min} min vs "
                    f"{self._model_report.baseline_mae_min} for nominal)")

        tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
        blocks = build_candidate_blocks(sc, tc, rb)
        feasible = feasible_pairs(sc.tasks, blocks)

        plans = {
            "baseline_fcfs": fcfs.schedule(sc, rb, blocks, feasible),
            "baseline_corridor": corridor.schedule(sc, rb, blocks, feasible),
            "greedy_coordinated": greedy.schedule(sc, rb, blocks, feasible),
        }
        planner = BlockPlanner(sc, rb, blocks, feasible, weights)
        planner.build()
        planner.add_hint(plans["greedy_coordinated"])
        plans["optimizer"] = planner.solve(max_seconds=time_limit)

        session = Session(key, sc, rb, tc, blocks, feasible, planner, plans,
                          weights, time_limit=time_limit, ml_note=note)
        with self._lock:
            if len(self._sessions) >= self._max:
                oldest = min(self._sessions.values(), key=lambda s: s.created)
                self._sessions.pop(oldest.key, None)
                self._building.pop(oldest.key, None)
            self._sessions[key] = session
        return session

    # -- serialisation ----------------------------------------------------
    def network(self, s: Session) -> dict:
        sc = s.scenario
        return {
            "name": sc.name,
            "horizonDays": sc.horizon_days,
            "stations": [{"code": st.code, "name": st.name, "km": st.km,
                          "line": st.line} for st in sc.stations],
            "sections": [{"id": x.id, "from": x.from_station, "to": x.to_station,
                          "kmFrom": x.km_from, "kmTo": x.km_to,
                          "lineType": x.line_type, "diversionFor": x.diversion_for}
                         for x in sc.sections],
            "corridorWindows": [{"sectionId": w.section_id, "start": w.start_min,
                                 "end": w.end_min} for w in sc.corridor_windows],
            "counts": {"assets": len(sc.assets), "tasks": len(sc.tasks),
                       "trains": len(sc.trains), "paths": len(sc.paths),
                       "candidateBlocks": len(s.blocks),
                       "feasiblePairs": sum(len(v) for v in s.feasible.values())},
            "mlNote": s.ml_note,
        }

    def train_paths(self, s: Session, route: str, day: int) -> list[dict]:
        prefix = {"MAIN": "MAIN", "BRANCH": "BRCH", "DIV": "DIV"}[route]
        ids = {x.id for x in s.scenario.sections if x.id.startswith(prefix)}
        lo, hi = day * MINUTES_PER_DAY, (day + 1) * MINUTES_PER_DAY
        klass = {t.number: t.train_class for t in s.scenario.trains}
        direction = {t.number: t.direction for t in s.scenario.trains}
        out: dict[str, dict] = {}
        for p in s.scenario.paths:
            if p.section_id not in ids or p.exit_min <= lo or p.enter_min >= hi:
                continue
            entry = out.setdefault(p.train_number, {
                "number": p.train_number, "trainClass": klass[p.train_number],
                "direction": direction[p.train_number], "segments": []})
            entry["segments"].append({"sectionId": p.section_id,
                                      "enter": p.enter_min, "exit": p.exit_min})
        for e in out.values():
            e["segments"].sort(key=lambda x: x["enter"])
        return list(out.values())

    def block_json(self, s: Session, b, tasks: dict) -> dict:
        members = [tasks[t] for t in b.task_ids]
        return {
            "id": b.id, "sectionId": b.section_id,
            "start": b.start_min, "end": b.end_min,
            "startLabel": stamp(b.start_min), "endLabel": hhmm(b.end_min),
            "durationMin": b.duration_min, "windowSource": b.window_source,
            "permits": sorted(b.permits), "departments": b.departments,
            "coordinated": b.is_coordinated,
            "trainCost": b.train_cost, "trainsAffected": len(b.trains_affected),
            "tasks": [{
                "id": t.id, "dept": t.dept, "activity": t.activity_type,
                "name": s.rulebook[t.activity_type].name, "severity": t.severity,
                "km": t.km_from, "durationMin": t.predicted_duration_min,
                "dueLabel": stamp(t.due_min), "risk": t.risk_score,
                "priority": t.priority_score,
                "overrunProbability": t.overrun_probability,
                "start": b.task_times.get(t.id, (b.start_min, 0))[0],
            } for t in members],
        }

    def plan_json(self, s: Session, method: str) -> dict:
        plan = s.plans[method]
        tasks = {t.id: t for t in s.scenario.tasks}
        m = evaluate(plan, s.scenario, s.rulebook, s.weights)
        return {
            "method": method, "label": METHOD_LABEL[method],
            "solverStatus": plan.solver_status,
            "objective": plan.objective_value, "bound": plan.best_bound,
            "gapPct": round(plan.gap_pct, 1), "solveSeconds": plan.solve_seconds,
            "blocks": [self.block_json(s, b, tasks) for b in plan.blocks],
            "deferred": [{
                "id": tid, "dept": tasks[tid].dept,
                "name": s.rulebook[tasks[tid].activity_type].name,
                "severity": tasks[tid].severity,
                "dueLabel": stamp(tasks[tid].due_min),
                "priority": tasks[tid].priority_score,
            } for tid in plan.unscheduled_task_ids],
            "metrics": m.as_row(),
            "valid": validate(plan, s.scenario, s.rulebook),
        }

    # -- features ---------------------------------------------------------
    def explain(self, s: Session, block_id: str) -> dict:
        plan = s.plans["optimizer"]
        block = next((b for b in plan.blocks if b.id == block_id), None)
        if block is None:
            raise KeyError(block_id)
        ex = explain_block(block, s.scenario, s.rulebook, s.traffic, s.weights)
        return {"blockId": block.id, "headline": ex.headline, "costs": ex.costs,
                "total": ex.total, "reasons": ex.reasons,
                "trainBreakdown": s.traffic.breakdown(block.section_id,
                                                      block.start_min, block.end_min)}

    def alternatives(self, s: Session, task_id: str, limit: int = 4) -> list[dict]:
        opts = alternatives_for(s.planner, task_id, s.plans["optimizer"], limit=limit)
        return [{"id": b.id, "sectionId": b.section_id,
                 "startLabel": stamp(b.start_min), "endLabel": hhmm(b.end_min),
                 "windowSource": b.window_source, "trainCost": b.train_cost}
                for b in opts]

    def counterfactual(self, s: Session, task_id: str, block_id: str,
                       seconds: float | None = None) -> dict:
        # Same budget as the base solve - see Session.time_limit.
        cf = counterfactual(s.planner, task_id, block_id, s.plans["optimizer"],
                            s.scenario, s.rulebook,
                            max_seconds=seconds or s.time_limit)
        return {"taskId": cf.task_id, "alternative": cf.alternative,
                "possible": cf.possible, "deltaObjective": cf.delta_objective,
                "deltaBlocks": cf.delta_blocks, "reasons": cf.reasons,
                "sentence": cf.sentence()}

    def whatif(self, s: Session, kind: str, n: int = 10,
               crew_type: str = "signal_team", section: str = "MAIN05",
               factor: float = 1.25, seconds: float | None = None) -> dict:
        sc, rb = s.scenario, s.rulebook
        base = s.plans["optimizer"]
        builders = {
            "freight": lambda: whatif.add_freight(sc, n=n),
            "crew": lambda: whatif.remove_crew(sc, crew_type, n),
            "urgent": lambda: whatif.urgent_defect(sc, rb, section),
            "durations": lambda: whatif.inflate_durations(sc, factor),
        }
        if kind not in builders:
            raise KeyError(kind)
        sc2, pert = builders[kind]()
        after = whatif.replan(sc2, rb, hint=base, anchor=base, weights=s.weights,
                              max_seconds=seconds or s.time_limit)
        d = whatif.diff(base, after, pert.detail)
        tasks = {t.id: t for t in sc2.tasks}
        return {
            "kind": pert.kind, "detail": pert.detail,
            "blocksBefore": d.blocks_before, "blocksAfter": d.blocks_after,
            "deferredBefore": d.deferred_before, "deferredAfter": d.deferred_after,
            "trainCostBefore": d.train_cost_before,
            "trainCostAfter": d.train_cost_after,
            "tasksMoved": [{"taskId": t, "from": a, "to": b}
                           for t, a, b in d.tasks_moved],
            "newlyDeferred": [{"id": t, "name": rb[tasks[t].activity_type].name,
                               "dept": tasks[t].dept, "severity": tasks[t].severity}
                              for t in d.tasks_newly_deferred if t in tasks],
            "newlyScheduled": d.tasks_newly_scheduled,
            "budgetSeconds": s.time_limit,
            "blocks": [self.block_json(s, b, tasks) for b in after.blocks],
            "summary": d.summary(),
        }

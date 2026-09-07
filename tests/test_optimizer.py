"""The model-validation suite from docs/05-optimizer.md.

These are cheap and they catch exactly the bugs that would otherwise surface on
stage: a block that opens with nothing in it, two gangs on the same metres of
track, a task scheduled past its deadline, an INFEASIBLE in front of judges.

Each test builds a tiny hand-made scenario so the expected answer is obvious.
"""

from __future__ import annotations

import pytest

from sanchay.core.candidates import (CandidateConfig, build_candidate_blocks,
                                     feasible_pairs)
from sanchay.core.models import Crew, Scenario, Section, Station, Task
from sanchay.core.rulebook import Rulebook
from sanchay.core.traffic_cost import TrafficCostModel
from sanchay.eval.metrics import validate
from sanchay.optimizer.cpsat import BlockPlanner, Weights


def tiny(tasks: list[Task], rb: Rulebook, line_type: str = "double") -> Scenario:
    """One section, no trains, a three-day horizon. Nothing to distract the solver."""
    stations = [Station("AA", "Aaa", 0.0, "MAIN"), Station("BB", "Bbb", 20.0, "MAIN")]
    sections = [Section("MAIN01", "AA", "BB", 0.0, 20.0, line_type)]
    crews = [Crew(f"{c}-{i}", "ENG", c, 0.0)
             for c in ("track_gang", "track_machine", "signal_team",
                       "ohe_team", "ohe_tower_car", "bridge_gang")
             for i in (1, 2)]
    return Scenario(name="tiny", seed=0, horizon_days=3, stations=stations,
                    sections=sections, assets=[], tasks=tasks, crews=crews,
                    trains=[], paths=[], corridor_windows=[])


def task(tid, activity, km, dur, due_day=3, dept="ENG", crew="track_gang",
         severity="important") -> Task:
    return Task(id=tid, dept=dept, activity_type=activity, asset_id="A1",
                section_id="MAIN01", km_from=km, km_to=km + 0.1, severity=severity,
                raised_min=0, due_min=due_day * 1440, nominal_duration_min=dur,
                crew_type=crew, risk_score=0.5, priority_score=30.0)


def solve(sc: Scenario, rb: Rulebook, weights: Weights | None = None, seconds=6.0):
    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    blocks = build_candidate_blocks(sc, tc, rb, CandidateConfig())
    feasible = feasible_pairs(sc.tasks, blocks)
    planner = BlockPlanner(sc, rb, blocks, feasible, weights)
    planner.build()
    return planner, planner.solve(max_seconds=seconds, workers=2)


# 1 ------------------------------------------------------------------------
def test_one_task_gets_one_block(rb):
    sc = tiny([task("ENG-1", "ENG_WELD_REPAIR", 5.0, 60)], rb)
    _, plan = solve(sc, rb)
    assert len(plan.blocks) == 1
    assert plan.blocks[0].task_ids == ["ENG-1"]
    assert not plan.unscheduled_task_ids


# 2 ------------------------------------------------------------------------
def test_compatible_work_is_coordinated_into_one_block(rb):
    """Three departments, same section, all compatible, plenty of room. If this
    returns three blocks the setup cost or constraint 2 is wrong."""
    sc = tiny([
        task("ENG-1", "ENG_WELD_REPAIR", 2.0, 60, dept="ENG", crew="track_gang"),
        task("SNT-1", "SNT_TRACK_CIRCUIT", 10.0, 60, dept="SNT", crew="signal_team"),
        task("TRD-1", "TRD_MAST_REPAIR", 18.0, 60, dept="TRD", crew="ohe_team"),
    ], rb)
    _, plan = solve(sc, rb)
    assert len(plan.blocks) == 1, f"expected coordination, got {len(plan.blocks)} blocks"
    assert plan.blocks[0].is_coordinated
    assert set(plan.blocks[0].departments) == {"ENG", "SNT", "TRD"}


# 3 ------------------------------------------------------------------------
def test_incompatible_activities_never_share_a_block(rb):
    sc = tiny([
        task("ENG-1", "ENG_TAMPING", 5.0, 60, crew="track_machine"),
        task("SNT-1", "SNT_POINT_OVERHAUL", 5.05, 60, dept="SNT", crew="signal_team"),
    ], rb)
    _, plan = solve(sc, rb)
    for b in plan.blocks:
        assert len(b.task_ids) == 1, "an explicitly unsafe pair was combined"


# 4 ------------------------------------------------------------------------
def test_a_task_cannot_work_under_a_permit_it_forbids(rb):
    """Signal testing needs the OHE live; the TRD job needs it isolated."""
    sc = tiny([
        task("SNT-1", "SNT_SIGNAL_TESTING", 4.0, 60, dept="SNT", crew="signal_team"),
        task("TRD-1", "TRD_OHE_INSULATOR", 15.0, 60, dept="TRD", crew="ohe_team"),
    ], rb)
    _, plan = solve(sc, rb)
    for b in plan.blocks:
        if len(b.task_ids) > 1:
            raise AssertionError("a power block was held over live signal testing")


# 5 ------------------------------------------------------------------------
def test_deadlines_are_respected(rb):
    sc = tiny([task("ENG-1", "ENG_WELD_REPAIR", 5.0, 60, due_day=1)], rb)
    _, plan = solve(sc, rb)
    assert plan.blocks[0].end_min <= 1440


# 6 ------------------------------------------------------------------------
def test_overconstrained_instance_defers_work_instead_of_failing(rb):
    """The unsched slack must make INFEASIBLE unreachable. This is the test
    that keeps a perturbed what-if from producing a red error on a projector."""
    tasks = [task(f"ENG-{i}", "ENG_BALLAST_SCREENING", 5.0, 240, due_day=1,
                  crew="track_machine") for i in range(1, 12)]
    sc = tiny(tasks, rb)
    _, plan = solve(sc, rb)
    assert plan.solver_status in ("OPTIMAL", "FEASIBLE")
    assert plan.unscheduled_task_ids, "expected some work to be deferred"
    assert len(plan.scheduled_task_ids) + len(plan.unscheduled_task_ids) == len(tasks)


# 7 ------------------------------------------------------------------------
def test_same_seed_gives_the_same_plan(rb):
    sc = tiny([task(f"ENG-{i}", "ENG_WELD_REPAIR", i * 2.0, 60) for i in range(1, 5)], rb)
    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    blocks = build_candidate_blocks(sc, tc, rb, CandidateConfig())
    feasible = feasible_pairs(sc.tasks, blocks)
    runs = []
    for _ in range(2):
        p = BlockPlanner(sc, rb, blocks, feasible)
        p.build()
        plan = p.solve(max_seconds=5, workers=1, seed=42)
        runs.append([(b.id, tuple(b.task_ids)) for b in plan.blocks])
    assert runs[0] == runs[1]


# 8 ------------------------------------------------------------------------
def test_raising_the_setup_cost_never_increases_the_block_count(rb):
    """A property test: the objective term that is supposed to drive
    coordination must actually drive it, and monotonically."""
    def three_jobs():
        return [task("ENG-1", "ENG_WELD_REPAIR", 2.0, 60),
                task("SNT-1", "SNT_TRACK_CIRCUIT", 12.0, 60, dept="SNT",
                     crew="signal_team"),
                task("TRD-1", "TRD_MAST_REPAIR", 18.0, 60, dept="TRD",
                     crew="ohe_team")]
    counts = []
    for setup in (0, 200, 800, 4000):
        _, plan = solve(tiny(three_jobs(), rb), rb, Weights(setup=setup))
        counts.append((setup, len(plan.blocks)))
    for (lo, a), (hi, b) in zip(counts, counts[1:]):
        assert b <= a, f"setup {lo} -> {hi} increased block count {a} -> {b}"
    assert counts[0][1] >= counts[-1][1]


# 9 ------------------------------------------------------------------------
def test_worksites_too_close_together_are_sequenced_not_parallel(rb):
    """Two jobs 50 m apart, each needing 200 m clearance, must not run at the
    same moment - though they may still share the block."""
    sc = tiny([
        task("ENG-1", "ENG_TAMPING", 5.00, 60, crew="track_machine"),
        task("ENG-2", "ENG_TAMPING", 5.05, 60, crew="track_machine"),
    ], rb)
    _, plan = solve(sc, rb)
    for b in plan.blocks:
        if len(b.task_ids) == 2:
            (s1, e1), (s2, e2) = (b.task_times["ENG-1"], b.task_times["ENG-2"])
            assert e1 <= s2 or e2 <= s1, "conflicting worksites ran simultaneously"


# 10 -----------------------------------------------------------------------
def test_a_section_and_its_diversion_are_never_blocked_together(rb):
    sc = tiny([task("ENG-1", "ENG_WELD_REPAIR", 5.0, 60)], rb)
    sc.sections.append(Section("DIV01", "AA", "BB", 0.0, 20.0, "single",
                               diversion_for="MAIN01"))
    sc.tasks.append(task("ENG-2", "ENG_WELD_REPAIR", 5.0, 60))
    sc.tasks[-1].section_id = "DIV01"
    _, plan = solve(sc, rb)
    main = [b for b in plan.blocks if b.section_id == "MAIN01"]
    div = [b for b in plan.blocks if b.section_id == "DIV01"]
    for a in main:
        for c in div:
            assert not (a.start_min < c.end_min and c.start_min < a.end_min)


# 11 -----------------------------------------------------------------------
def test_full_scenario_plan_passes_the_hard_constraint_audit(pipeline):
    sc, rb, _tc, blocks, feasible = pipeline
    planner = BlockPlanner(sc, rb, blocks, feasible)
    planner.build()
    plan = planner.solve(max_seconds=8, workers=2)
    assert validate(plan, sc, rb) == []

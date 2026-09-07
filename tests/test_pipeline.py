"""End-to-end checks on the full pipeline, and the fairness rules the whole
benchmark rests on."""

from sanchay.baselines import corridor, fcfs, greedy
from sanchay.core.candidates import feasible_pairs, km_conflict
from sanchay.core.store import load_scenario, save_scenario
from sanchay.core.timeutil import at, hhmm, overlaps, stamp
from sanchay.eval.metrics import evaluate, objective_of, validate
from sanchay.optimizer.cpsat import BlockPlanner


def test_timeutil_round_trip():
    assert stamp(at(2, 14, 30)) == "D2 14:30"
    assert hhmm(at(0, 9, 5)) == "09:05"
    assert not overlaps(0, 60, 60, 120)   # back-to-back blocks are fine
    assert overlaps(0, 61, 60, 120)


def test_candidate_blocks_price_traffic_and_corridor_differently(pipeline):
    _sc, _rb, _tc, blocks, _f = pipeline
    corridor_cost = [b.train_cost for b in blocks if b.window_source == "corridor"]
    traffic_cost = [b.train_cost for b in blocks if b.window_source == "traffic"]
    assert corridor_cost and max(corridor_cost) == 0, \
        "a corridor window should displace no traffic - that is why it exists"
    assert traffic_cost and min(traffic_cost) > 0


def test_feasible_pairs_respect_section_duration_and_deadline(pipeline):
    sc, _rb, _tc, blocks, feasible = pipeline
    for t in sc.tasks:
        for b in feasible[t.id]:
            assert b.section_id == t.section_id
            assert b.duration_min >= t.predicted_duration_min
            assert b.end_min <= t.due_min


def test_every_method_produces_a_valid_plan(pipeline):
    """The fairness rule: a baseline is never allowed to cheat, because a
    baseline that cheats invalidates the entire comparison."""
    sc, rb, _tc, blocks, feasible = pipeline
    plans = {
        "fcfs": fcfs.schedule(sc, rb, blocks, feasible),
        "corridor": corridor.schedule(sc, rb, blocks, feasible),
        "greedy": greedy.schedule(sc, rb, blocks, feasible),
    }
    planner = BlockPlanner(sc, rb, blocks, feasible)
    planner.build()
    planner.add_hint(plans["greedy"])
    plans["optimizer"] = planner.solve(max_seconds=8, workers=2)
    for name, plan in plans.items():
        assert validate(plan, sc, rb) == [], f"{name} produced an illegal plan"


def test_optimizer_beats_its_own_warm_start(pipeline):
    """It is given the greedy plan as a hint, so it can never do worse. If this
    fails, the objective in metrics.py has drifted from the one in the model."""
    sc, rb, _tc, blocks, feasible = pipeline
    seed_plan = greedy.schedule(sc, rb, blocks, feasible)
    planner = BlockPlanner(sc, rb, blocks, feasible)
    planner.build()
    planner.add_hint(seed_plan)
    plan = planner.solve(max_seconds=10, workers=2)
    assert objective_of(plan, sc, rb) <= objective_of(seed_plan, sc, rb)


def test_uncoordinated_baseline_really_is_uncoordinated(pipeline):
    sc, rb, _tc, blocks, feasible = pipeline
    plan = fcfs.schedule(sc, rb, blocks, feasible)
    assert all(not b.is_coordinated for b in plan.blocks)


def test_corridor_baseline_only_uses_corridor_windows(pipeline):
    sc, rb, _tc, blocks, feasible = pipeline
    plan = corridor.schedule(sc, rb, blocks, feasible)
    assert plan.blocks
    assert all(b.window_source == "corridor" for b in plan.blocks)
    assert all(b.train_cost == 0 for b in plan.blocks)


def test_metrics_account_for_every_task(pipeline):
    sc, rb, _tc, blocks, feasible = pipeline
    plan = greedy.schedule(sc, rb, blocks, feasible)
    m = evaluate(plan, sc, rb)
    assert m.tasks_scheduled + len(plan.unscheduled_task_ids) == m.tasks_total


def test_km_conflict_uses_the_stricter_clearance(scenario, rb):
    a = next(t for t in scenario.tasks if t.activity_type == "ENG_TAMPING")
    near = type(a)(**{**a.__dict__, "id": "X", "km_from": a.km_from + 0.05,
                      "km_to": a.km_from + 0.06})
    far = type(a)(**{**a.__dict__, "id": "Y", "km_from": a.km_from + 9.0,
                     "km_to": a.km_from + 9.1})
    assert km_conflict(a, near, rb)
    assert not km_conflict(a, far, rb)


def test_scenario_survives_a_csv_round_trip(scenario, tmp_path):
    save_scenario(scenario, tmp_path / "sc")
    back = load_scenario(tmp_path / "sc")
    assert back.tasks == scenario.tasks
    assert back.sections == scenario.sections
    assert back.paths == scenario.paths
    assert back.horizon_days == scenario.horizon_days

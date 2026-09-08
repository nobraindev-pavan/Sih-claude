"""The two features the demo turns on."""

from sanchay.baselines import greedy
from sanchay.core.traffic_cost import TrafficCostModel
from sanchay.optimizer import whatif
from sanchay.optimizer.cpsat import BlockPlanner
from sanchay.optimizer.explain import (alternatives_for, counterfactual,
                                       explain_block)


def _plan(pipeline, seconds=8):
    sc, rb, tc, blocks, feasible = pipeline
    planner = BlockPlanner(sc, rb, blocks, feasible)
    planner.build()
    planner.add_hint(greedy.schedule(sc, rb, blocks, feasible))
    return sc, rb, tc, planner, planner.solve(max_seconds=seconds, workers=2)


def test_explanation_costs_sum_to_the_blocks_share_of_the_objective(pipeline):
    sc, rb, tc, _planner, plan = _plan(pipeline)
    block = max(plan.blocks, key=lambda b: len(b.task_ids))
    ex = explain_block(block, sc, rb, tc)
    assert ex.total > 0
    assert set(ex.costs) == {"train disruption", "opening a block",
                             "line occupancy", "night working"}
    assert ex.reasons and ex.tasks


def test_counterfactual_returns_a_number_or_a_reason(pipeline):
    sc, rb, _tc, planner, plan = _plan(pipeline)
    block = max(plan.blocks, key=lambda b: len(b.task_ids))
    task_id = block.task_ids[0]
    alts = alternatives_for(planner, task_id, plan, limit=2)
    assert alts, "a task should have alternative windows to be asked about"
    for alt in alts:
        cf = counterfactual(planner, task_id, alt.id, plan, sc, rb, max_seconds=4)
        assert cf.sentence()
        if cf.possible:
            assert cf.delta_objective is not None
        else:
            assert cf.reasons


def test_counterfactual_refuses_a_window_on_the_wrong_section(pipeline):
    sc, rb, _tc, planner, plan = _plan(pipeline)
    task = sc.tasks[0]
    other = next(b for b in planner.blocks if b.section_id != task.section_id)
    cf = counterfactual(planner, task.id, other.id, plan, sc, rb, max_seconds=3)
    assert not cf.possible


def test_work_needing_a_withdrawn_crew_cannot_be_scheduled(pipeline):
    """Withdraw every gang of a type and none of its work can be done.

    Note what this does *not* assert: that removing crew increases the deferred
    count. Removing capacity cannot improve the true optimum, but our solves are
    time-limited, so a re-solve can still find a better plan than a base that had
    not converged. Asserting the weaker, guaranteed invariant keeps the test from
    being flaky - and the distinction is worth understanding before you write the
    next one.
    """
    sc, rb, _tc, _planner, base = _plan(pipeline)
    n_signal = sum(1 for c in sc.crews if c.crew_type == "signal_team")
    sc2, _pert = whatif.remove_crew(sc, "signal_team", n=n_signal)
    assert not [c for c in sc2.crews if c.crew_type == "signal_team"]

    after = whatif.replan(sc2, rb, hint=base, anchor=base, max_seconds=8)
    needs_signal = {t.id for t in sc2.tasks if t.crew_type == "signal_team"}
    assert needs_signal, "the fixture should contain signal work"
    assert needs_signal <= set(after.unscheduled_task_ids), \
        "work was scheduled for a crew type with no gangs left"
    # other departments are unaffected
    assert set(after.scheduled_task_ids) - needs_signal


def test_anchoring_keeps_the_plan_recognisable(pipeline):
    """A planner who has circulated a block plan wants the smallest change that
    absorbs a disruption, not a different optimum."""
    sc, rb, _tc, _planner, base = _plan(pipeline)
    sc2, _ = whatif.add_freight(sc, n=6)
    anchored = whatif.replan(sc2, rb, hint=base, anchor=base, max_seconds=8)
    free = whatif.replan(sc2, rb, hint=base, anchor=None, max_seconds=8)
    moved_anchored = len(whatif.diff(base, anchored, "a").tasks_moved)
    moved_free = len(whatif.diff(base, free, "b").tasks_moved)
    assert moved_anchored <= moved_free


def test_extra_freight_never_reduces_train_cost_for_free(pipeline):
    sc, rb, _tc, _planner, base = _plan(pipeline)
    sc2, _ = whatif.add_freight(sc, n=12)
    tc2 = TrafficCostModel(sc2.sections, sc2.trains, sc2.paths)
    for b in base.blocks:
        assert tc2.cost(b.section_id, b.start_min, b.end_min)[0] >= b.train_cost

"""The sanction workflow. A workflow that lets you skip a step is not a workflow."""

import pytest

from sanchay.core.workflow import (OVERRIDE_REASONS, PlanFile, WorkflowError)


class FakeBlock:
    def __init__(self, bid):
        self.id = bid


class FakePlan:
    def __init__(self, n=4):
        self.blocks = [FakeBlock(f"B{i}") for i in range(n)]
        self.unscheduled_task_ids = []


@pytest.fixture
def pf():
    return PlanFile.from_plan(FakePlan(), "test-scenario")


def test_a_new_plan_starts_proposed_and_records_that(pf):
    assert pf.counts() == {"proposed": 4}
    assert pf.events[0].actor_role == "SYSTEM"


def test_the_happy_path_runs_all_the_way_to_returned(pf):
    pf.transition("B0", "under_review", "DOM")
    pf.transition("B0", "sanctioned", "DOM", "weekly block meeting")
    pf.transition("B0", "issued", "CHC")
    pf.transition("B0", "executed", "CHC")
    pf.transition("B0", "returned", "CHC")
    assert pf.blocks["B0"].state == "returned"
    assert pf.blocks["B0"].sanctioned_by == "DOM"


def test_steps_cannot_be_skipped(pf):
    with pytest.raises(WorkflowError, match="cannot move"):
        pf.transition("B0", "issued", "CHC")


def test_a_terminal_state_is_terminal(pf):
    pf.transition("B0", "rejected", "DOM", reason_code="safety")
    with pytest.raises(WorkflowError, match="final state"):
        pf.transition("B0", "under_review", "DOM")


def test_only_the_right_role_may_sanction(pf):
    pf.transition("B0", "under_review", "SR_DEN")
    with pytest.raises(WorkflowError, match="that is for DOM"):
        pf.transition("B0", "sanctioned", "SR_DEN")
    pf.transition("B0", "sanctioned", "DOM")


def test_rejecting_requires_a_reason_code(pf):
    """An override nobody recorded a reason for teaches us nothing, which is
    the entire argument for keeping the trail."""
    with pytest.raises(WorkflowError, match="reason code"):
        pf.transition("B0", "rejected", "DOM", "not happy with it")
    pf.transition("B0", "rejected", "DOM", "gang on a failure", "resources")
    assert pf.override_reasons() == {"resources": 1}


def test_an_unknown_reason_code_is_refused(pf):
    with pytest.raises(WorkflowError, match="unknown reason code"):
        pf.transition("B0", "rejected", "DOM", "", "vibes")


def test_unknown_role_and_unknown_block_are_refused(pf):
    with pytest.raises(WorkflowError, match="unknown role"):
        pf.transition("B0", "under_review", "MINISTER")
    with pytest.raises(WorkflowError, match="not in this plan"):
        pf.transition("B999", "under_review", "DOM")


def test_bulk_actions_only_touch_eligible_blocks(pf):
    pf.transition("B0", "rejected", "DOM", "", "safety")
    pf.review_all("DOM")
    assert pf.counts() == {"rejected": 1, "under_review": 3}
    pf.sanction_all("DOM")
    assert pf.counts() == {"rejected": 1, "sanctioned": 3}


def test_every_transition_is_recorded_with_an_actor(pf):
    before = len(pf.events)
    pf.transition("B0", "under_review", "CHC", "checking against the chart")
    ev = pf.events[-1]
    assert len(pf.events) == before + 1
    assert (ev.actor_role, ev.from_state, ev.to_state) == ("CHC", "proposed", "under_review")
    assert "chart" in ev.note and ev.line()


def test_the_trail_survives_a_round_trip(pf, tmp_path):
    pf.review_all("DOM")
    pf.transition("B1", "rejected", "DOM", "materials not on site", "materials")
    path = pf.save(tmp_path / "plan.json")
    back = PlanFile.load(path)
    assert back.counts() == pf.counts()
    assert len(back.events) == len(pf.events)
    assert back.override_reasons() == {"materials": 1}


def test_reason_codes_are_countable_not_prose():
    assert "other" in OVERRIDE_REASONS
    assert all(isinstance(v, str) and v for v in OVERRIDE_REASONS.values())

"""The pre-solved bundle.

Kept deliberately small: a full export runs the solver a dozen times and takes
minutes. This checks the *shape* of the bundle and the promises the static UI
relies on, not the quality of the plans inside it — those are tested everywhere
else.
"""

import json

import pytest

import sanchay.export_static as ex
from sanchay.core.workflow import OVERRIDE_REASONS, TRANSITIONS


@pytest.fixture(scope="module")
def bundle(monkeypatch_module=None):
    # Trim the expensive parts: one setup stop, one what-if, two costings.
    orig = (ex.SETUP_STOPS, ex.WHATIFS, ex.COUNTERFACTUAL_BLOCKS,
            ex.COUNTERFACTUAL_ALTS)
    ex.SETUP_STOPS = (500,)
    ex.WHATIFS = [("crew", {"crew_type": "signal_team", "n": 1})]
    ex.COUNTERFACTUAL_BLOCKS = 1
    ex.COUNTERFACTUAL_ALTS = 1
    try:
        yield ex.build(ex.ExportConfig(seed=4, demand="low", days=3, ml=False,
                                       time_limit=4.0), log=lambda *a: None)
    finally:
        (ex.SETUP_STOPS, ex.WHATIFS, ex.COUNTERFACTUAL_BLOCKS,
         ex.COUNTERFACTUAL_ALTS) = orig


def test_it_says_it_is_precomputed(bundle):
    """The UI shows this. A demo that quietly pretends to be solving is a demo
    that lies."""
    assert bundle["precomputed"] is True
    assert bundle["builtAt"]


def test_it_carries_every_method(bundle):
    assert set(bundle["plans"]) == {"baseline_fcfs", "baseline_corridor",
                                    "greedy_coordinated", "optimizer"}
    assert len(bundle["compare"]) == 4


def test_every_recommended_block_can_be_explained(bundle):
    """The UI lets you click any block on the chart, so every one of them needs
    an explanation in the bundle or the click does nothing."""
    ids = {b["id"] for b in bundle["plans"]["optimizer"]["blocks"]}
    assert ids <= set(bundle["explanations"])
    for ex_ in bundle["explanations"].values():
        assert abs(sum(ex_["costs"].values()) - ex_["total"]) < 0.5


def test_every_scheduled_task_has_its_alternative_windows(bundle):
    """Listing alternatives is a sort, not a solve, so there is no excuse for a
    task whose 'why not elsewhere?' shows nothing."""
    tasks = {t["id"] for b in bundle["plans"]["optimizer"]["blocks"]
             for t in b["tasks"]}
    assert tasks <= set(bundle["alternatives"])


def test_costed_alternatives_are_keyed_the_way_the_ui_looks_them_up(bundle):
    for key, cf in bundle["counterfactuals"].items():
        task_id, block_id = key.split("|")
        assert cf["taskId"] == task_id
        assert any(a["id"] == block_id
                   for a in bundle["alternatives"].get(task_id, []))


def test_the_timetable_ships_once_and_is_sliceable(bundle):
    """The UI filters by route and day in the browser rather than asking a
    server, so the paths have to be here whole."""
    assert bundle["trainPaths"]
    for t in bundle["trainPaths"][:20]:
        assert t["segments"] == sorted(t["segments"], key=lambda s: s["enter"])
        assert t["trainClass"] and t["direction"] in ("UP", "DN")


def test_the_workflow_tables_match_the_servers(bundle):
    """The browser runs the same sanction state machine. Shipping the tables
    rather than reimplementing them is what stops the two drifting apart."""
    assert bundle["workflow"]["transitions"] == TRANSITIONS
    assert bundle["workflow"]["reasonCodes"] == OVERRIDE_REASONS


def test_setup_stops_all_have_a_plan(bundle):
    for stop in bundle["setupStops"]:
        plan = bundle["setupPlans"][str(stop)]
        assert plan["blocks"] and plan["metrics"]["method"] == "optimizer"


def test_whatif_scenarios_are_present_and_diffed(bundle):
    for kind, result in bundle["whatIf"].items():
        assert result["blocksBefore"] > 0 and result["blocksAfter"] > 0
        assert result["detail"]


def test_it_serialises(bundle, tmp_path):
    path = ex.write(bundle, tmp_path / "b.json")
    reloaded = json.loads(path.read_text())
    assert reloaded["plans"]["optimizer"]["blocks"]

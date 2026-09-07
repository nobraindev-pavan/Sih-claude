"""The risk model, and the ablation machinery."""

import numpy as np
import pytest

from sanchay.gen.asset_history import HIDDEN, HistoryConfig, generate_history
from sanchay.ml.risk import FEATURES, RiskModel, apply_risk, temporal_split


@pytest.fixture(scope="module")
def history(scenario):
    return generate_history(scenario, HistoryConfig(seed=5, months=18))


@pytest.fixture(scope="module")
def trained(history):
    train, test = temporal_split(history, train_months=13)
    return RiskModel().fit(train), test


def test_the_confounders_are_withheld_from_the_model():
    """They exist in the CSV so a reviewer can confirm they were withheld. If
    they leaked into FEATURES the model would recover our own arithmetic and
    every number it produced would be meaningless."""
    assert not set(FEATURES) & set(HIDDEN)


def test_the_split_is_temporal_not_random(history):
    train, test = temporal_split(history, train_months=13)
    assert max(int(r["month_index"]) for r in train) < \
        min(int(r["month_index"]) for r in test)


def test_maintenance_is_endogenous(history):
    """A defect draws attention, which resets days-since-maintenance. The model
    has to learn from a history shaped by the interventions it informs."""
    by_asset = {}
    for r in history:
        by_asset.setdefault(r["asset_id"], []).append(r)
    resets = 0
    for rows in by_asset.values():
        rows.sort(key=lambda r: int(r["month_index"]))
        for a, b in zip(rows, rows[1:]):
            if int(a["defect_within_30d"]) and \
               int(b["days_since_maintenance"]) < int(a["days_since_maintenance"]):
                resets += 1
    assert resets > 0


def test_the_monsoon_raises_the_defect_rate(history):
    wet = [int(r["defect_within_30d"]) for r in history if int(r["is_monsoon"])]
    dry = [int(r["defect_within_30d"]) for r in history if not int(r["is_monsoon"])]
    assert np.mean(wet) > np.mean(dry)


def test_predictions_are_probabilities_that_discriminate(trained):
    model, test = trained
    p = model.predict(test)
    y = np.array([int(r["defect_within_30d"]) for r in test])
    assert p.min() >= 0 and p.max() <= 1
    assert p[y == 1].mean() > p[y == 0].mean()


def test_shap_contributions_sum_to_the_raw_prediction(trained):
    """The property that makes TreeSHAP an explanation rather than a heuristic
    ranking. Worth checking, because it is easy to plot the wrong array."""
    model, test = trained
    sample = test[:200]
    contrib = model.shap(sample)
    assert contrib.shape[1] == len(FEATURES) + 1     # + base value
    raw = np.log(model.predict(sample) / (1 - model.predict(sample)))
    assert np.allclose(contrib.sum(axis=1), raw, atol=1e-4)


def test_the_report_states_the_baseline_and_judges_against_it(trained):
    model, test = trained
    rep = model.evaluate(test)
    assert 0.5 < rep.baseline_auc <= 1.0
    assert rep.verdict()
    # the verdict must reflect the numbers, not a hardcoded boast
    if rep.auc <= rep.baseline_auc + 0.005 and rep.brier >= rep.baseline_brier - 0.001:
        assert "SIMPLE RULE WINS" in rep.verdict()


def test_apply_risk_replaces_the_generators_ground_truth(scenario, trained):
    """Until this runs, risk_score is the generator's own hazard — the scenario
    handing the optimizer information a real division does not have."""
    model, _ = trained
    before = [(t.risk_score, t.priority_score) for t in scenario.tasks]
    try:
        apply_risk(scenario, model)
        after = [(t.risk_score, t.priority_score) for t in scenario.tasks]
        assert after != before
        assert all(0.0 <= t.risk_score <= 1.0 for t in scenario.tasks)
        assert all(t.priority_score > 0 for t in scenario.tasks)
    finally:
        for t, (r, p) in zip(scenario.tasks, before):
            t.risk_score, t.priority_score = r, p


def test_forbidding_coordination_makes_the_plan_worse(rb):
    """The core ablation: the solver keeps the same candidates, rulebook and
    objective, and loses only the ability to combine departments."""
    from sanchay.eval.ablations import run
    rows = run(seeds=(1,), time_limit=6, studies=("coordination",))
    allowed = next(r for r in rows if r.setting == "coordination allowed")
    forbidden = next(r for r in rows if r.setting == "coordination forbidden")
    assert forbidden.n_coordinated == 0
    assert allowed.n_coordinated > 0
    assert allowed.n_blocks < forbidden.n_blocks
    assert allowed.objective < forbidden.objective
    assert allowed.invalid == 0 and forbidden.invalid == 0

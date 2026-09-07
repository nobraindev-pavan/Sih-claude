"""The duration model. Kept fast: trained once per session on the fixture log."""

import numpy as np
import pytest

from sanchay.gen.execution_log import LogConfig, generate_log
from sanchay.ml.duration import (CATEGORICAL, NUMERIC, DurationModel, _split,
                                 apply_predictions)


@pytest.fixture(scope="module")
def log(scenario, rb):
    return generate_log(scenario, rb, LogConfig(seed=11, n_records=1600))


@pytest.fixture(scope="module")
def trained(log):
    train, test = _split(log)
    return DurationModel(quantile=0.8).fit(train), test


def test_outcomes_are_never_features():
    """The one mistake that would invalidate every number the model produces."""
    leaks = {"actual_duration_min", "overran", "overrun_min", "overrun_reason"}
    assert not (set(NUMERIC) | set(CATEGORICAL)) & leaks


def test_the_split_does_not_put_the_same_block_on_both_sides(log):
    train, test = _split(log)
    assert train and test
    assert not {r["block_id"] for r in train} & {r["block_id"] for r in test}


def test_it_beats_predicting_the_nominal_duration(trained):
    model, test = trained
    y = np.array([float(r["actual_duration_min"]) for r in test])
    nominal = np.array([float(r["nominal_duration_min"]) for r in test])
    pred = model.predict(test, quantile=False)
    assert np.abs(y - pred).mean() < np.abs(y - nominal).mean(), \
        "if the model cannot beat the nominal duration, use the nominal duration"


def test_the_p80_is_above_the_median_and_covers_roughly_four_in_five(trained):
    model, test = trained
    med = model.predict(test, quantile=False)
    p80 = model.predict(test, quantile=True)
    assert (p80 >= med).mean() > 0.9
    y = np.array([float(r["actual_duration_min"]) for r in test])
    coverage = (y <= p80).mean()
    assert 0.68 < coverage < 0.92, f"P80 covered {coverage:.0%}, expected near 80%"


def test_overrun_probabilities_are_probabilities_and_discriminate(trained):
    model, test = trained
    prob = model.predict_overrun(test)
    assert prob.min() >= 0.0 and prob.max() <= 1.0
    over = np.array([int(r["overran"]) for r in test])
    assert prob[over == 1].mean() > prob[over == 0].mean()


def test_predictions_reach_the_optimizer(scenario, rb, trained):
    """The whole point of this model: it changes the plan, not a slide."""
    model, _ = trained
    before = [t.predicted_duration_min for t in scenario.tasks]
    apply_predictions(scenario, rb, model, quantile=True)
    after = [t.predicted_duration_min for t in scenario.tasks]
    try:
        assert after != before, "apply_predictions did not change any duration"
        assert all(t.overrun_probability > 0 for t in scenario.tasks)
        cap = rb.policy.max_block_duration_min
        assert all(15 <= t.predicted_duration_min <= cap for t in scenario.tasks)
    finally:
        for t, d in zip(scenario.tasks, before):   # leave the fixture as we found it
            t.predicted_duration_min = d
            t.overrun_probability = 0.0

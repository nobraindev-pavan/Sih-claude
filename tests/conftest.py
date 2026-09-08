"""Shared fixtures. A small scenario so the suite stays fast."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sanchay.core.candidates import build_candidate_blocks, feasible_pairs  # noqa: E402
from sanchay.core.rulebook import Rulebook  # noqa: E402
from sanchay.core.traffic_cost import TrafficCostModel  # noqa: E402
from sanchay.gen.generate import GenConfig, generate  # noqa: E402


@pytest.fixture(scope="session")
def rb():
    return Rulebook.load()


@pytest.fixture(scope="session")
def scenario(rb):
    return generate(GenConfig(seed=1, horizon_days=3, demand="low"), rb)


@pytest.fixture(scope="session")
def pipeline(scenario, rb):
    tc = TrafficCostModel(scenario.sections, scenario.trains, scenario.paths)
    blocks = build_candidate_blocks(scenario, tc, rb)
    return scenario, rb, tc, blocks, feasible_pairs(scenario.tasks, blocks)

"""The HTTP layer. Small budgets so the suite stays usable."""

import pytest
from fastapi.testclient import TestClient

from sanchay.api.main import app

Q = {"seed": 3, "demand": "low", "days": 3, "timeLimit": 5}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def solved(client):
    """Solve once for the whole module - each distinct parameter set costs a solve."""
    return client.get("/api/plan", params={**Q, "method": "optimizer"}).json()


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_scenario_describes_the_network(client):
    net = client.get("/api/scenario", params=Q).json()["network"]
    assert net["counts"]["tasks"] > 0
    assert net["counts"]["candidateBlocks"] > net["counts"]["tasks"]
    assert any(s["lineType"] == "single" for s in net["sections"])
    assert any(s["diversionFor"] for s in net["sections"])


def test_plan_is_valid_and_complete(solved):
    assert solved["valid"] == [], "the API served a plan that breaks a hard constraint"
    scheduled = sum(len(b["tasks"]) for b in solved["blocks"])
    assert scheduled + len(solved["deferred"]) == solved["metrics"]["tasks_total"]


def test_every_method_is_comparable_in_one_round_trip(client):
    rows = client.get("/api/compare", params=Q).json()["rows"]
    assert {r["method"] for r in rows} == {
        "baseline_fcfs", "baseline_corridor", "greedy_coordinated", "optimizer"}


def test_unknown_method_is_a_404(client):
    assert client.get("/api/plan", params={**Q, "method": "wishful"}).status_code == 404


def test_bad_demand_is_a_400(client):
    assert client.get("/api/scenario", params={**Q, "demand": "enormous"}).status_code == 400


def test_traingraph_is_scoped_to_one_route_and_day(client):
    g = client.get("/api/traingraph", params={**Q, "route": "MAIN", "day": 1}).json()
    assert all(s["id"].startswith("MAIN") for s in g["sections"])
    lo, hi = 1440, 2880
    assert all(w["start"] < hi and w["end"] > lo for w in g["corridorWindows"])
    assert g["trains"], "day 1 of the main corridor should carry trains"


def test_explain_returns_a_decomposition_not_prose(client, solved):
    block = max(solved["blocks"], key=lambda b: len(b["tasks"]))
    ex = client.get("/api/explain", params={**Q, "blockId": block["id"]}).json()
    assert abs(sum(ex["costs"].values()) - ex["total"]) < 0.5
    assert ex["reasons"]


def test_explain_on_an_unplanned_block_is_a_404(client):
    assert client.get("/api/explain", params={**Q, "blockId": "B999999"}).status_code == 404


def test_counterfactual_answers_with_a_number_or_a_reason(client, solved):
    block = max(solved["blocks"], key=lambda b: len(b["tasks"]))
    task_id = block["tasks"][0]["id"]
    alts = client.get("/api/alternatives",
                      params={**Q, "taskId": task_id}).json()["alternatives"]
    assert alts
    cf = client.post("/api/counterfactual", params=Q,
                     json={"taskId": task_id, "blockId": alts[0]["id"]}).json()
    assert cf["sentence"]
    assert cf["possible"] is False or cf["deltaObjective"] is not None


def test_whatif_reuses_the_base_plans_budget(client):
    """Otherwise the reported difference is partly extra search time, not the
    perturbation - the easiest way to lie with this tool."""
    r = client.post("/api/whatif", params=Q,
                    json={"kind": "crew", "n": 1}).json()
    assert r["budgetSeconds"] == Q["timeLimit"]
    assert r["blocksBefore"] > 0 and r["blocksAfter"] > 0
    assert "signal_team" in r["detail"]


def test_unknown_whatif_is_a_400(client):
    assert client.post("/api/whatif", params=Q,
                       json={"kind": "sunspots"}).status_code == 400


def test_rulebook_is_served_with_its_caveat(client):
    rb = client.get("/api/rulebook").json()
    assert len(rb["activities"]) >= 12
    assert "not reviewed" in rb["note"].lower()
    testing = next(a for a in rb["activities"] if a["code"] == "SNT_SIGNAL_TESTING")
    assert "power_block" in testing["forbids"]


def test_concurrent_requests_for_one_world_solve_it_once(client):
    """The cache stampede that made the optimizer look bad: three parallel
    requests each starting their own solve, competing for CPU, and a badly
    under-converged plan winning the cache."""
    import concurrent.futures as cf

    from sanchay.api.main import service
    params = {**Q, "seed": 77}
    with cf.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(client.get, "/api/plan", params=params) for _ in range(3)]
        results = [f.result().json() for f in futures]
    assert all(r["valid"] == [] for r in results)
    blocks = {len(r["blocks"]) for r in results}
    assert len(blocks) == 1, f"parallel requests produced different plans: {blocks}"
    key = service.key_for(77, Q["demand"], Q["days"], False, service.solve(
        seed=77, demand=Q["demand"], days=Q["days"], time_limit=Q["timeLimit"]).weights)
    assert key in service._sessions

"""HTTP API.

Thin on purpose: every endpoint hands off to `PlanningService`, which has no
HTTP in it. That keeps the interesting logic testable without a client and
means the CLI and the API cannot drift apart.

    uvicorn sanchay.api.main:app --reload
    python -m sanchay serve

If `ui/dist` exists it is served at `/`, so a built frontend and the API come
from one origin and there is no CORS to explain on stage.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..optimizer.cpsat import Weights
from .service import METHOD_LABEL, PlanningService

app = FastAPI(title="SANCHAY", version="0.1.0",
              description="Coordinated railway maintenance block planning. "
                          "All data is simulated.")
# The Vite dev server runs on another port; in production the UI is served
# from this app, so this only matters while developing.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])

service = PlanningService()
UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"


class Scenario(BaseModel):
    seed: int = 1
    demand: str = "normal"
    days: int = 7
    ml: bool = False
    timeLimit: float = 12.0
    train: int = Weights.train
    setup: int = Weights.setup
    downtime: int = Weights.downtime
    overdue: int = Weights.overdue
    risk: int = Weights.risk
    night: int = Weights.night

    def weights(self) -> Weights:
        return Weights(train=self.train, setup=self.setup, downtime=self.downtime,
                       overdue=self.overdue, risk=self.risk, night=self.night)


def _params(seed: int = 1, demand: str = "normal", days: int = 7, ml: bool = False,
            timeLimit: float = 12.0, train: int = 1, setup: int = 500,
            downtime: int = 2, overdue: int = 50, risk: int = 200,
            night: int = 20) -> Scenario:
    return Scenario(seed=seed, demand=demand, days=days, ml=ml, timeLimit=timeLimit,
                    train=train, setup=setup, downtime=downtime, overdue=overdue,
                    risk=risk, night=night)


def _session(p: Scenario):
    if p.demand not in ("low", "normal", "surge"):
        raise HTTPException(400, "demand must be low, normal or surge")
    if not 1 <= p.days <= 14:
        raise HTTPException(400, "days must be between 1 and 14")
    return service.solve(seed=p.seed, demand=p.demand, days=p.days, ml=p.ml,
                         weights=p.weights(),
                         time_limit=min(max(p.timeLimit, 1.0), 60.0))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "methods": list(METHOD_LABEL)}


@app.get("/api/scenario")
def scenario(p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    s = _session(p)
    return {"network": service.network(s),
            "methods": [{"id": k, "label": v} for k, v in METHOD_LABEL.items()],
            "weights": s.weights.as_dict()}


@app.get("/api/plan")
def plan(method: str = "optimizer",
         p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    if method not in METHOD_LABEL:
        raise HTTPException(404, f"unknown method {method}")
    return service.plan_json(_session(p), method)


@app.get("/api/compare")
def compare(p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    """Every method's metrics — the comparison table, in one round trip."""
    s = _session(p)
    return {"rows": [service.plan_json(s, m)["metrics"] for m in METHOD_LABEL],
            "labels": METHOD_LABEL}


@app.get("/api/traingraph")
def traingraph(route: str = "MAIN", day: int = 1,
               p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    if route not in ("MAIN", "BRANCH", "DIV"):
        raise HTTPException(400, "route must be MAIN, BRANCH or DIV")
    s = _session(p)
    net = service.network(s)
    prefix = {"MAIN": "MAIN", "BRANCH": "BRCH", "DIV": "DIV"}[route]
    lo, hi = day * 1440, (day + 1) * 1440
    return {
        "route": route, "day": day, "dayStart": lo,
        "sections": [x for x in net["sections"] if x["id"].startswith(prefix)],
        "corridorWindows": [w for w in net["corridorWindows"]
                            if w["sectionId"].startswith(prefix)
                            and w["start"] < hi and w["end"] > lo],
        "trains": service.train_paths(s, route, day),
    }


@app.get("/api/explain")
def explain(blockId: str, p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    try:
        return service.explain(_session(p), blockId)
    except KeyError:
        raise HTTPException(404, f"block {blockId} is not in the current plan")


@app.get("/api/alternatives")
def alternatives(taskId: str, limit: int = 4,
                 p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    return {"taskId": taskId,
            "alternatives": service.alternatives(_session(p), taskId, limit)}


class CounterfactualBody(BaseModel):
    taskId: str
    blockId: str
    #: Omit to reuse the base plan's budget, which is what keeps the comparison
    #: honest. Override only when you deliberately want a longer search.
    seconds: float | None = None


@app.post("/api/counterfactual")
def counterfactual(body: CounterfactualBody,
                   p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    secs = None if body.seconds is None else min(max(body.seconds, 1.0), 60.0)
    return service.counterfactual(_session(p), body.taskId, body.blockId, seconds=secs)


class WhatIfBody(BaseModel):
    kind: str = Field(description="freight | crew | urgent | durations")
    n: int = 10
    crewType: str = "signal_team"
    section: str = "MAIN05"
    factor: float = 1.25
    seconds: float | None = None


@app.post("/api/whatif")
def what_if(body: WhatIfBody,
            p: Scenario = Query(default_factory=Scenario)) -> dict:  # noqa: B008
    try:
        secs = None if body.seconds is None else min(max(body.seconds, 1.0), 60.0)
        return service.whatif(_session(p), body.kind, n=body.n,
                              crew_type=body.crewType, section=body.section,
                              factor=body.factor, seconds=secs)
    except KeyError:
        raise HTTPException(400, f"unknown what-if kind {body.kind}")


@app.get("/api/rulebook")
def rulebook() -> dict:
    """The safety rules, so the UI can show them rather than assert them."""
    rb = service.rulebook
    return {
        "activities": [{
            "code": a.code, "dept": a.dept, "name": a.name,
            "requires": sorted(a.requires), "forbids": sorted(a.forbids),
            "nominalDurationMin": a.nominal_duration_min,
            "minSeparationM": a.min_separation_m, "crewType": a.crew_type,
        } for a in rb.activities.values()],
        "policy": {"maxBlockDurationMin": rb.policy.max_block_duration_min,
                   "minBlockDurationMin": rb.policy.min_block_duration_min,
                   "nightStartHour": rb.policy.night_start_hour,
                   "nightEndHour": rb.policy.night_end_hour},
        "note": ("Derived from published sources and simplified for the "
                 "prototype. Not reviewed by a serving railway officer."),
    }


if UI_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(UI_DIST / "index.html")

"""Bake a pre-solved demo into a JSON bundle the UI can run without a backend.

Why this exists: the solver needs fifteen-odd seconds of CPU per scenario, which
is fine on a laptop and wrong behind an HTTP request on a free host. For a demo
that has to be openable by anyone, from a link, on a phone, in a hall with bad
wifi, the right architecture is not a smaller solver - it is no solver. Solve
everything once here, ship the answers, and let the page be a page.

What gets precomputed:

  * the network, the timetable, and all four methods' plans
  * an explanation for every block in the optimizer's plan
  * the alternative windows for *every* task - listing them is only a sort over
    the feasible pairs, so it costs nothing
  * the *cost* of a curated set of those alternatives. Each one is a full
    re-solve, so they cannot all be precomputed; the UI says so where a costing
    is missing rather than inventing a number
  * all four what-if scenarios
  * plans at several block-setup weights, so the slider still moves the plan

Everything else - the sanction workflow, the day and route selectors, the
comparison table - is either client-side already or a slice of what is here.

The bundle is labelled `precomputed: true` and the UI says so on the page. A
demo that quietly pretends to be solving is a demo that lies.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .api.service import METHOD_LABEL, PlanningService
from .core.workflow import OVERRIDE_REASONS, ROLES, TRANSITIONS
from .optimizer.cpsat import Weights

#: Block-setup weights the slider snaps to. Each one is a full solve.
SETUP_STOPS = (0, 250, 500, 1000, 2000)
#: What-if scenarios, matching the UI's buttons.
WHATIFS = [
    ("freight", {"n": 10}),
    ("crew", {"crew_type": "signal_team", "n": 1}),
    ("urgent", {"section": "MAIN05"}),
    ("durations", {"factor": 1.25}),
]
#: How many blocks get their alternatives costed. Each alternative is a re-solve.
COUNTERFACTUAL_BLOCKS = 6
COUNTERFACTUAL_ALTS = 2


@dataclass
class ExportConfig:
    seed: int = 1
    demand: str = "normal"
    days: int = 7
    ml: bool = True
    time_limit: float = 20.0
    out: Path = Path("ui/public/demo-bundle.json")


def build(cfg: ExportConfig | None = None, log=print) -> dict:
    cfg = cfg or ExportConfig()
    svc = PlanningService(max_sessions=16)
    t0 = time.time()

    log(f"solving base scenario (seed {cfg.seed}, {cfg.demand}, "
        f"ml={cfg.ml}, {cfg.time_limit}s)…")
    base = svc.solve(seed=cfg.seed, demand=cfg.demand, days=cfg.days, ml=cfg.ml,
                     weights=Weights(), time_limit=cfg.time_limit)

    bundle: dict = {
        "precomputed": True,
        "builtAt": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "params": {"seed": cfg.seed, "demand": cfg.demand, "days": cfg.days,
                   "ml": cfg.ml, "timeLimit": cfg.time_limit},
        "network": svc.network(base),
        "methods": [{"id": k, "label": v} for k, v in METHOD_LABEL.items()],
        "weights": Weights().as_dict(),
        "plans": {},
        "compare": [],
        "trainPaths": [],
        "explanations": {},
        "alternatives": {},
        "counterfactuals": {},
        "whatIf": {},
        "setupStops": list(SETUP_STOPS),
        "setupPlans": {},
        "rulebook": None,
        "workflow": {"transitions": TRANSITIONS, "roles": ROLES,
                     "reasonCodes": OVERRIDE_REASONS},
    }

    # -- plans and metrics ------------------------------------------------
    for method in METHOD_LABEL:
        pj = svc.plan_json(base, method)
        bundle["plans"][method] = pj
        bundle["compare"].append(pj["metrics"])
    log(f"  {len(bundle['plans']['optimizer']['blocks'])} blocks in the "
        f"optimizer plan")

    # -- the timetable, shipped once and sliced in the browser ------------
    sc = base.scenario
    klass = {t.number: t.train_class for t in sc.trains}
    direction = {t.number: t.direction for t in sc.trains}
    by_train: dict[str, dict] = {}
    for p in sc.paths:
        e = by_train.setdefault(p.train_number, {
            "number": p.train_number, "trainClass": klass[p.train_number],
            "direction": direction[p.train_number], "segments": []})
        e["segments"].append({"sectionId": p.section_id,
                              "enter": p.enter_min, "exit": p.exit_min})
    for e in by_train.values():
        e["segments"].sort(key=lambda s: s["enter"])
    bundle["trainPaths"] = list(by_train.values())
    log(f"  {len(bundle['trainPaths'])} train paths")

    # -- explanations for every block in the recommended plan -------------
    for b in bundle["plans"]["optimizer"]["blocks"]:
        bundle["explanations"][b["id"]] = svc.explain(base, b["id"])
    log(f"  {len(bundle['explanations'])} block explanations")

    # -- alternatives for every task: a sort, not a solve, so it is free ---
    for b in bundle["plans"]["optimizer"]["blocks"]:
        for task in b["tasks"]:
            bundle["alternatives"][task["id"]] = svc.alternatives(
                base, task["id"], limit=4)
    log(f"  alternative windows listed for {len(bundle['alternatives'])} tasks")

    # -- costing them is a re-solve each, so only a curated set -----------
    blocks = sorted(bundle["plans"]["optimizer"]["blocks"],
                    key=lambda b: -len(b["tasks"]))[:COUNTERFACTUAL_BLOCKS]
    n_cf = 0
    for b in blocks:
        for task in b["tasks"][:1]:
            tid = task["id"]
            for alt in bundle["alternatives"].get(tid, [])[:COUNTERFACTUAL_ALTS]:
                key = f"{tid}|{alt['id']}"
                bundle["counterfactuals"][key] = svc.counterfactual(
                    base, tid, alt["id"], seconds=cfg.time_limit)
                n_cf += 1
                log(f"  costed {n_cf}: {tid} -> {alt['startLabel']}")

    # -- what-if ----------------------------------------------------------
    for kind, kwargs in WHATIFS:
        log(f"  what-if: {kind}")
        bundle["whatIf"][kind] = svc.whatif(base, kind, seconds=cfg.time_limit,
                                            **kwargs)

    # -- the setup-weight slider stops ------------------------------------
    for setup in SETUP_STOPS:
        if setup == Weights().setup:
            bundle["setupPlans"][str(setup)] = bundle["plans"]["optimizer"]
            continue
        log(f"  setup weight {setup}")
        s = svc.solve(seed=cfg.seed, demand=cfg.demand, days=cfg.days, ml=cfg.ml,
                      weights=Weights(setup=setup), time_limit=cfg.time_limit)
        bundle["setupPlans"][str(setup)] = svc.plan_json(s, "optimizer")

    # -- the rulebook, so the page can show the rules rather than assert them
    rb = svc.rulebook
    bundle["rulebook"] = {
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

    bundle["buildSeconds"] = round(time.time() - t0, 1)
    log(f"built in {bundle['buildSeconds']:.0f}s")
    return bundle


def write(bundle: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, separators=(",", ":")))
    return path

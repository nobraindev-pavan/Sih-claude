"""The benchmark. One command, N scenarios, an honest table.

The protocol (docs/07-evaluation.md), and each piece of it is there to close a
hole a judge would otherwise poke:

  * **Every method draws from the same candidate blocks** and is checked by the
    same validator. A baseline is never offered a worse menu, and a plan that
    breaks a hard rule is reported as invalid rather than scored.
  * **Paired comparison.** The same seed produces the same world for every
    method, so we compare per-scenario differences rather than two group means.
    Much more powerful, and it lets us report a win rate - "fewer blocks in 87
    of 90 scenarios" persuades more than any percentage.
  * **Mean +/- 95% CI** on the paired deltas.
  * **Three demand levels**, because a method that only wins on easy instances
    has not won.
"""

from __future__ import annotations

import csv
import math
import statistics
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..baselines import corridor, fcfs, greedy
from ..core.candidates import CandidateConfig, build_candidate_blocks, feasible_pairs
from ..core.rulebook import Rulebook
from ..core.traffic_cost import TrafficCostModel
from ..gen.generate import GenConfig, generate
from ..optimizer.cpsat import BlockPlanner, Weights
from .metrics import Metrics, evaluate, validate

METHODS = ("baseline_fcfs", "baseline_corridor", "greedy_coordinated", "optimizer")
#: Metrics where a smaller number is better. Used to orient every delta so a
#: positive "improvement" always means the optimizer did better.
LOWER_IS_BETTER = {
    "n_blocks", "total_block_minutes", "train_cost", "trains_affected",
    "residual_overdue_risk", "blocks_per_task_done", "objective",
}
HEADLINE = ("n_blocks", "train_cost", "completion_pct", "critical_completion_pct",
            "total_block_minutes", "blocks_per_task_done", "objective")


@dataclass
class RunConfig:
    scenarios: int = 10
    demands: tuple[str, ...] = ("low", "normal", "surge")
    horizon_days: int = 7
    time_limit: float = 10.0
    weights: Weights = field(default_factory=Weights)
    jobs: int = 4
    #: Total CPU search workers to divide among parallel scenarios.
    solver_workers: int = 8
    out_dir: Path | None = None


def run_one(args: tuple[int, str, float, dict, int]) -> list[dict]:
    """One scenario, all four methods. Kept top-level so it can be pickled."""
    seed, demand, time_limit, wdict, workers = args
    rb = Rulebook.load()
    weights = Weights(**wdict)
    sc = generate(GenConfig(seed=seed, demand=demand), rb)
    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    blocks = build_candidate_blocks(sc, tc, rb, CandidateConfig())
    feasible = feasible_pairs(sc.tasks, blocks)

    plans = {
        "baseline_fcfs": fcfs.schedule(sc, rb, blocks, feasible),
        "baseline_corridor": corridor.schedule(sc, rb, blocks, feasible),
        "greedy_coordinated": greedy.schedule(sc, rb, blocks, feasible),
    }
    planner = BlockPlanner(sc, rb, blocks, feasible, weights)
    planner.build()
    planner.add_hint(plans["greedy_coordinated"])
    plans["optimizer"] = planner.solve(max_seconds=time_limit, workers=workers)

    rows = []
    for name, plan in plans.items():
        problems = validate(plan, sc, rb)
        row = evaluate(plan, sc, rb, weights).as_row()
        row.update(seed=seed, demand=demand, n_tasks=len(sc.tasks),
                   n_candidates=len(blocks), invalid=len(problems),
                   first_problem=problems[0] if problems else "")
        rows.append(row)
    return rows


def run(cfg: RunConfig) -> list[dict]:
    # Each CpSolver defaults to eight search workers. Running scenarios in
    # parallel without dividing that budget starves every solve and quietly
    # makes the optimizer look no better than the greedy that seeded it.
    workers = max(1, cfg.solver_workers // max(1, cfg.jobs))
    jobs = [(seed, demand, cfg.time_limit, cfg.weights.as_dict(), workers)
            for seed in range(1, cfg.scenarios + 1)
            for demand in cfg.demands]
    rows: list[dict] = []
    if cfg.jobs > 1:
        with ProcessPoolExecutor(max_workers=cfg.jobs) as pool:
            for i, out in enumerate(pool.map(run_one, jobs), 1):
                rows.extend(out)
                print(f"  scenario {i}/{len(jobs)} done", flush=True)
    else:
        for i, job in enumerate(jobs, 1):
            rows.extend(run_one(job))
            print(f"  scenario {i}/{len(jobs)} done", flush=True)
    return rows


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _ci95(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return (values[0] if values else 0.0), 0.0
    mean = statistics.fmean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return mean, half


def paired_deltas(rows: list[dict], metric: str, method: str,
                  against: str) -> list[float]:
    """Per-scenario improvement of `method` over `against`, oriented so that
    positive always means better."""
    index = {(r["seed"], r["demand"], r["method"]): r for r in rows}
    keys = sorted({(r["seed"], r["demand"]) for r in rows})
    out = []
    for seed, demand in keys:
        a = index.get((seed, demand, method))
        b = index.get((seed, demand, against))
        if a is None or b is None:
            continue
        raw = a[metric] - b[metric]          # method minus comparator
        out.append(-raw if metric in LOWER_IS_BETTER else raw)
    return out


def summarise(rows: list[dict], method: str = "optimizer") -> str:
    lines: list[str] = []
    invalid = sum(r["invalid"] for r in rows)
    n_scen = len({(r["seed"], r["demand"]) for r in rows})
    lines.append(f"Scenarios: {n_scen}   Methods: {len(METHODS)}   "
                 f"Hard-constraint violations: {invalid}")
    if invalid:
        first = next(r for r in rows if r["invalid"])
        lines.append(f"  !! {first['method']} seed {first['seed']}: {first['first_problem']}")
    lines.append("")

    lines.append("PER-METHOD MEANS")
    head = f"{'method':20s}" + "".join(f"{m[:13]:>15s}" for m in HEADLINE)
    lines.append(head)
    for m in METHODS:
        sub = [r for r in rows if r["method"] == m]
        if not sub:
            continue
        cells = "".join(f"{statistics.fmean(r[k] for r in sub):15.1f}" for k in HEADLINE)
        lines.append(f"{m:20s}{cells}")
    lines.append("")

    for against in ("baseline_fcfs", "baseline_corridor", "greedy_coordinated"):
        lines.append(f"PAIRED: {method} vs {against}   (positive = optimizer better)")
        lines.append(f"  {'metric':26s}{'mean delta':>14s}{'95% CI':>16s}{'win rate':>11s}")
        for k in HEADLINE:
            d = paired_deltas(rows, k, method, against)
            if not d:
                continue
            mean, half = _ci95(d)
            wins = sum(1 for v in d if v > 0)
            ties = sum(1 for v in d if v == 0)
            lines.append(f"  {k:26s}{mean:14.1f}{'+/- ' + format(half, '.1f'):>16s}"
                         f"{f'{wins}/{len(d)}':>11s}" + ("  (ties " + str(ties) + ")" if ties else ""))
        lines.append("")
    return "\n".join(lines)


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

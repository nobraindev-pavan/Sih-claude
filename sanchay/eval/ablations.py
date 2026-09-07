"""Ablations. Testing our own contributions instead of assuming them.

Five studies, each answering a question a technical judge will ask:

  coordination   Forbid multi-department blocks. How much of the win is the
                 core idea, and how much is just having a solver?
  pareto         Sweep the block setup cost from 0 to 2000 and trace the
                 frontier between separate blocks and train disruption. This is
                 the chart that shows the objective is a real trade-off surface
                 rather than a number we tuned until it looked good.
  anytime        Objective against solver time limit. Justifies the ten-second
                 demo budget instead of asserting it. Rows marked with a star
                 are the warm-start fallback: the budget expired before the
                 solver found anything, so they show the floor rather than the
                 method.
  screening      Candidate pre-screening (`keep_per_slot`). Shows what our
                 documented heuristic costs.
  durations      Nominal against the model's P80. The ML layer's effect on the
                 plan, separate from its effect on execution (that one lives in
                 ml/value_experiment.py).

Run with `python -m sanchay ablate`. Each study writes a row per configuration
so the numbers can be replotted without re-running the solver.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from ..baselines import greedy
from ..core.candidates import CandidateConfig, build_candidate_blocks, feasible_pairs
from ..core.rulebook import Rulebook
from ..core.traffic_cost import TrafficCostModel
from ..gen.generate import GenConfig, generate
from ..optimizer.cpsat import BlockPlanner, Weights
from .metrics import evaluate, validate

SETUP_SWEEP = (0, 100, 250, 500, 1000, 2000)
TIME_SWEEP = (1.0, 3.0, 10.0, 30.0)
SCREEN_SWEEP = (1, 2, 4, 8)


@dataclass
class AblationRow:
    study: str
    setting: str
    seed: int
    n_blocks: int
    n_coordinated: int
    total_block_minutes: int
    train_cost: float
    completion_pct: float
    critical_completion_pct: float
    objective: float
    gap_pct: float
    solve_seconds: float
    invalid: int
    #: The solver's own status. A row whose status names a fallback is the
    #: greedy warm start, not the optimizer - reporting it as an optimizer
    #: result would attribute the greedy plan's numbers to the wrong method.
    status: str = ""


def _solve(sc, rb, weights: Weights, cand_cfg: CandidateConfig,
           time_limit: float, forbid_coordination: bool = False):
    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    blocks = build_candidate_blocks(sc, tc, rb, cand_cfg)
    feasible = feasible_pairs(sc.tasks, blocks)
    planner = BlockPlanner(sc, rb, blocks, feasible, weights)
    model = planner.build()
    if forbid_coordination:
        # At most one department per block. This is the ablation: the solver
        # keeps everything else - the same candidates, the same rulebook, the
        # same objective - and loses only the ability to combine departments.
        for b in planner.blocks:
            members = [t for t in sc.tasks if (t.id, b.id) in planner.x]
            depts = {t.dept for t in members}
            if len(depts) < 2:
                continue
            for dept in depts:
                lit = model.NewBoolVar(f"used_{b.id}_{dept}")
                for t in members:
                    if t.dept == dept:
                        model.Add(lit >= planner.x[(t.id, b.id)])
                planner.__dict__.setdefault("_dept_lits", {}).setdefault(b.id, []).append(lit)
            model.Add(sum(planner.__dict__["_dept_lits"][b.id]) <= 1)
    planner.add_hint(greedy.schedule(sc, rb, blocks, feasible))
    plan = planner.solve(max_seconds=time_limit)
    return plan, sc


def _row(study: str, setting: str, seed: int, plan, sc, rb, weights) -> AblationRow:
    m = evaluate(plan, sc, rb, weights)
    return AblationRow(
        study=study, setting=setting, seed=seed, n_blocks=m.n_blocks,
        n_coordinated=m.n_coordinated_blocks,
        total_block_minutes=m.total_block_minutes, train_cost=m.train_cost,
        completion_pct=m.completion_pct,
        critical_completion_pct=m.critical_completion_pct,
        objective=m.objective, gap_pct=m.gap_pct, solve_seconds=m.solve_seconds,
        invalid=len(validate(plan, sc, rb)), status=plan.solver_status)


def run(seeds=(1, 2, 3), time_limit: float = 12.0,
        studies=("coordination", "pareto", "anytime", "screening", "durations"),
        ) -> list[AblationRow]:
    rb = Rulebook.load()
    rows: list[AblationRow] = []
    base_cand = CandidateConfig()

    for seed in seeds:
        sc = generate(GenConfig(seed=seed), rb)

        if "coordination" in studies:
            for label, forbid in (("coordination allowed", False),
                                  ("coordination forbidden", True)):
                plan, s2 = _solve(sc, rb, Weights(), base_cand, time_limit, forbid)
                rows.append(_row("coordination", label, seed, plan, s2, rb, Weights()))

        if "pareto" in studies:
            for setup in SETUP_SWEEP:
                w = Weights(setup=setup)
                plan, s2 = _solve(sc, rb, w, base_cand, time_limit)
                rows.append(_row("pareto", f"setup={setup}", seed, plan, s2, rb, w))

        if "anytime" in studies:
            for tl in TIME_SWEEP:
                plan, s2 = _solve(sc, rb, Weights(), base_cand, tl)
                rows.append(_row("anytime", f"limit={tl:g}s", seed, plan, s2, rb, Weights()))

        if "screening" in studies:
            for keep in SCREEN_SWEEP:
                cfg = replace(base_cand, keep_per_slot=keep)
                plan, s2 = _solve(sc, rb, Weights(), cfg, time_limit)
                rows.append(_row("screening", f"keep={keep}", seed, plan, s2, rb, Weights()))

        if "durations" in studies:
            from ..ml.duration import apply_predictions
            from ..ml.duration import train_and_report as train_dur
            model, _ = train_dur()
            for label, use_ml in (("nominal", False), ("model P80", True)):
                world = generate(GenConfig(seed=seed), rb)
                if use_ml:
                    apply_predictions(world, rb, model, quantile=True)
                plan, s2 = _solve(world, rb, Weights(), base_cand, time_limit)
                rows.append(_row("durations", label, seed, plan, s2, rb, Weights()))
    return rows


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _mean(rows, attr):
    return sum(getattr(r, attr) for r in rows) / len(rows)


def summarise(rows: list[AblationRow]) -> str:
    out: list[str] = [
        "Objective values are only comparable WITHIN a study. The pareto sweep",
        "changes the objective's own weights, so its objective column compares",
        "plans against different yardsticks - read blocks against train cost there,",
        "not the objective.", ""]
    studies = []
    for r in rows:
        if r.study not in studies:
            studies.append(r.study)
    for study in studies:
        sub = [r for r in rows if r.study == study]
        settings = []
        for r in sub:
            if r.setting not in settings:
                settings.append(r.setting)
        out.append(f"### {study}")
        head = (f"  {'setting':24s}{'blocks':>8s}{'coord':>7s}{'blk min':>9s}"
                f"{'train cost':>12s}{'done %':>8s}{'crit %':>8s}"
                f"{'objective':>12s}{'gap %':>8s}")
        out.append(head)
        out.append("  " + "-" * (len(head) - 2))
        for setting in settings:
            g = [r for r in sub if r.setting == setting]
            out.append(
                f"  {setting:24s}{_mean(g, 'n_blocks'):8.1f}"
                f"{_mean(g, 'n_coordinated'):7.1f}"
                f"{_mean(g, 'total_block_minutes'):9.0f}"
                f"{_mean(g, 'train_cost'):12.0f}"
                f"{_mean(g, 'completion_pct'):8.1f}"
                f"{_mean(g, 'critical_completion_pct'):8.1f}"
                f"{_mean(g, 'objective'):12.0f}"
                f"{_mean(g, 'gap_pct'):8.1f}"
                + ("   * warm-start fallback"
                   if any("fell back" in r.status for r in g) else ""))
        bad = sum(r.invalid for r in sub)
        if bad:
            out.append(f"  !! {bad} configuration(s) produced an invalid plan")
        if any("fell back" in r.status for r in sub):
            out.append("  * the time limit expired before the solver found anything, so "
                       "these rows are the")
            out.append("    greedy warm start rather than an optimizer result - "
                       "read them as the floor, not the method")
        out.append("")
    return "\n".join(out)


def pareto_svg(rows: list[AblationRow], width: int = 620, height: int = 380) -> str:
    """Separate blocks against weighted train disruption, as the setup cost varies.

    One axis is what a planner is trying to reduce; the other is what it costs
    to reduce it. Every point is a legitimate plan - which is the argument that
    our objective is a trade-off surface a division can choose a point on, not a
    single number we tuned until it flattered us.
    """
    pts = []
    for setting in dict.fromkeys(r.setting for r in rows if r.study == "pareto"):
        g = [r for r in rows if r.study == "pareto" and r.setting == setting]
        pts.append((setting, _mean(g, "n_blocks"), _mean(g, "train_cost")))
    if not pts:
        return "<svg/>"

    pad = {"l": 66, "r": 108, "t": 20, "b": 44}
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    x_lo, x_hi = min(xs) * 0.92, max(xs) * 1.05
    y_lo, y_hi = 0, max(ys) * 1.12 or 1
    X = lambda v: pad["l"] + (v - x_lo) / (x_hi - x_lo) * (width - pad["l"] - pad["r"])
    Y = lambda v: height - pad["b"] - (v - y_lo) / (y_hi - y_lo) * (height - pad["t"] - pad["b"])

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'font-family="ui-monospace, Menlo, monospace" font-size="10">']
    for i in range(5):
        v = y_lo + (y_hi - y_lo) * i / 4
        parts.append(f'<line x1="{pad["l"]}" y1="{Y(v):.1f}" x2="{width - pad["r"]}" '
                     f'y2="{Y(v):.1f}" stroke="#D5DAD4"/>')
        parts.append(f'<text x="{pad["l"] - 8}" y="{Y(v) + 3.5:.1f}" fill="#6C777C" '
                     f'text-anchor="end">{v:.0f}</text>')
    path = " ".join(f"{X(b):.1f},{Y(t):.1f}" for _, b, t in
                    sorted(pts, key=lambda p: p[1]))
    parts.append(f'<polyline points="{path}" fill="none" stroke="#1D4E77" stroke-width="1.6"/>')
    for setting, b, t in pts:
        parts.append(f'<circle cx="{X(b):.1f}" cy="{Y(t):.1f}" r="4" fill="#1D4E77"/>')
        parts.append(f'<text x="{X(b) + 8:.1f}" y="{Y(t) + 3.5:.1f}" fill="#3E474B">'
                     f'{setting}</text>')
    parts.append(f'<text x="{(width - pad["r"] + pad["l"]) / 2:.0f}" y="{height - 10}" '
                 f'fill="#6C777C" text-anchor="middle">separate blocks (fewer is better)</text>')
    parts.append(f'<text x="16" y="{height / 2:.0f}" fill="#6C777C" text-anchor="middle" '
                 f'transform="rotate(-90 16 {height / 2:.0f})">weighted train disruption</text>')
    parts.append("</svg>")
    return "".join(parts)


def write_csv(rows: list[AblationRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(vars(rows[0])))
        w.writeheader()
        for r in rows:
            w.writerow(vars(r))

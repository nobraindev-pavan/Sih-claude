"""Command line for SANCHAY.

    python -m sanchay gen                 build and save a scenario
    python -m sanchay plan                run every method, compare, draw
    python -m sanchay explain             why this block, and why not that one
    python -m sanchay whatif              perturb an assumption and re-optimise
    python -m sanchay bench               the full benchmark

Every command is seeded and reproducible. `--help` on any of them.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .baselines import corridor, fcfs, greedy
from .core.candidates import build_candidate_blocks, feasible_pairs
from .core.rulebook import Rulebook
from .core.timeutil import stamp
from .core.traffic_cost import TrafficCostModel
from .eval.metrics import evaluate, validate
from .gen.execution_log import LogConfig, generate_log, write_log
from .gen.generate import GenConfig, generate
from .optimizer.cpsat import BlockPlanner, Weights

DATA = Path("data/scenarios")
OUT = Path("out")
LABEL = {"baseline_fcfs": "B1 uncoordinated (FCFS)",
         "baseline_corridor": "B2 corridor policy",
         "greedy_coordinated": "greedy coordination",
         "optimizer": "SANCHAY optimizer"}


def _pipeline(args, rb: Rulebook):
    sc = generate(GenConfig(seed=args.seed, demand=args.demand,
                            horizon_days=args.days), rb)
    if getattr(args, "ml", False):
        from .ml.duration import apply_predictions, train_and_report
        from .ml.risk import apply_risk
        from .ml.risk import train_and_report as train_risk
        model, rep = train_and_report()
        apply_predictions(sc, rb, model, quantile=True)
        print(f"planning to the model's P{int(model.quantile * 100)} durations "
              f"(MAE {rep.mae_min} min vs {rep.baseline_mae_min} for nominal)")
        risk_model, risk_rep = train_risk()
        apply_risk(sc, risk_model)
        print(f"risk scores from the model (AUC {risk_rep.auc}, "
              f"Brier {risk_rep.brier}; simple rule {risk_rep.baseline_auc}/"
              f"{risk_rep.baseline_brier}) rather than the generator's hazard")
    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    blocks = build_candidate_blocks(sc, tc, rb)
    feasible = feasible_pairs(sc.tasks, blocks)
    return sc, tc, blocks, feasible


def _table(rows: list[dict]) -> str:
    cols = [("method", 24, "s"), ("n_blocks", 8, "d"), ("n_coordinated_blocks", 7, "d"),
            ("total_block_minutes", 9, "d"), ("train_cost", 10, ".0f"),
            ("completion_pct", 8, ".1f"), ("critical_completion_pct", 8, ".1f"),
            ("utilisation_pct", 8, ".1f"), ("objective", 11, ".0f")]
    head = "".join(f"{c[:w].rjust(w) if f != 's' else c[:w].ljust(w)} "
                   for c, w, f in cols)
    lines = [head, "-" * len(head)]
    for r in rows:
        cells = []
        for c, w, f in cols:
            v = LABEL.get(r[c], r[c]) if c == "method" else r[c]
            cells.append(f"{v:<{w}}" if f == "s" else f"{v:>{w}{f}}")
        lines.append(" ".join(cells))
    return "\n".join(lines)


# --- commands --------------------------------------------------------------

def cmd_gen(args) -> int:
    from .core.store import save_scenario
    rb = Rulebook.load()
    sc = generate(GenConfig(seed=args.seed, demand=args.demand,
                            horizon_days=args.days), rb)
    out = DATA / args.name
    save_scenario(sc, out)
    rows = generate_log(sc, rb, LogConfig(seed=args.seed + 900, n_records=args.log_rows))
    write_log(rows, out / "execution_log.csv")
    from .gen.asset_history import HistoryConfig, generate_history, write_history
    hist = generate_history(sc, HistoryConfig(seed=args.seed + 700,
                                              months=args.history_months))
    write_history(hist, out / "asset_history.csv")
    print(f"{sc.name} -> {out}")
    print(f"  {len(sc.sections)} sections, {len(sc.assets)} assets, "
          f"{len(sc.tasks)} open tasks, {len(sc.trains)} train paths")
    print(f"  {len(rows)} historical block executions for the duration model")
    print(f"  {len(hist)} monthly asset condition snapshots for the risk model")
    print("  SIMULATED DATA - schema-compatible with TMS/SMMS/TDMS/COA, not from them")
    return 0


def cmd_plan(args) -> int:
    rb = Rulebook.load()
    sc, tc, blocks, feasible = _pipeline(args, rb)
    print(f"{sc.name}: {len(sc.tasks)} tasks, {len(sc.trains)} train paths, "
          f"{len(blocks)} candidate blocks, "
          f"{sum(len(v) for v in feasible.values())} feasible (task, block) pairs")

    plans = {
        "baseline_fcfs": fcfs.schedule(sc, rb, blocks, feasible),
        "baseline_corridor": corridor.schedule(sc, rb, blocks, feasible),
        "greedy_coordinated": greedy.schedule(sc, rb, blocks, feasible),
    }
    planner = BlockPlanner(sc, rb, blocks, feasible, Weights())
    planner.build()
    planner.add_hint(plans["greedy_coordinated"])
    t0 = time.time()
    plans["optimizer"] = planner.solve(max_seconds=args.time_limit, log=args.verbose)
    print(f"solver: {planner.stats.status} in {time.time() - t0:.1f}s, "
          f"objective {planner.stats.objective:.0f}, "
          f"bound {planner.stats.bound:.0f} "
          f"(gap {plans['optimizer'].gap_pct:.1f}%)\n")

    rows = []
    for name, plan in plans.items():
        problems = validate(plan, sc, rb)
        if problems:
            print(f"!! {name} violates hard constraints:")
            for p in problems[:5]:
                print(f"   {p}")
        rows.append(evaluate(plan, sc, rb).as_row())
    print(_table(rows))
    print("\nAll figures simulated. Lower is better for blocks, block minutes, "
          "train cost and objective.")

    if args.html:
        from .viz.traingraph import render_comparison
        OUT.mkdir(exist_ok=True)
        titled = {LABEL[k]: v for k, v in plans.items() if k != "greedy_coordinated"}
        path = OUT / args.html
        path.write_text(render_comparison(
            sc, titled, rows, route=args.route, day=args.day,
            title=f"Vijaypur Division - block plan comparison (seed {args.seed})"))
        print(f"\nwrote {path}  (open it in a browser)")
    return 0


def cmd_explain(args) -> int:
    from .optimizer.explain import alternatives_for, counterfactual, explain_block
    rb = Rulebook.load()
    sc, tc, blocks, feasible = _pipeline(args, rb)
    seed_plan = greedy.schedule(sc, rb, blocks, feasible)
    planner = BlockPlanner(sc, rb, blocks, feasible)
    planner.build()
    planner.add_hint(seed_plan)
    plan = planner.solve(max_seconds=args.time_limit)

    chosen = [b for b in plan.blocks if b.is_coordinated] or plan.blocks
    chosen.sort(key=lambda b: -len(b.task_ids))
    block = next((b for b in plan.blocks if b.id == args.block), chosen[0])

    ex = explain_block(block, sc, rb, tc)
    print("WHY THIS BLOCK")
    print(f"  {ex.headline}")
    print(f"  tasks: {', '.join(ex.tasks)}")
    print(f"  window source: {block.window_source}   "
          f"permits: {', '.join(sorted(block.permits)) or 'none'}")
    print("\n  cost breakdown")
    for k, v in ex.costs.items():
        bar = "#" * min(40, int(v / max(1.0, ex.total) * 40))
        print(f"    {k:20s} {v:9.1f}  {bar}")
    print(f"    {'TOTAL':20s} {ex.total:9.1f}")
    print("\n  reasons")
    for r in ex.reasons:
        print(f"    - {r}")

    task_id = args.task or block.task_ids[0]
    print(f"\nWHY NOT ANOTHER WINDOW FOR {task_id}")
    for alt in alternatives_for(planner, task_id, plan, limit=args.alternatives):
        cf = counterfactual(planner, task_id, alt.id, plan, sc, rb,
                            max_seconds=args.time_limit / 2)
        print(f"  {alt.section_id} {stamp(alt.start_min)}-"
              f"{stamp(alt.end_min).split()[1]} ({alt.window_source})")
        print(f"    {cf.sentence()}")
    return 0


def cmd_whatif(args) -> int:
    from .optimizer import whatif
    rb = Rulebook.load()
    sc = generate(GenConfig(seed=args.seed, demand=args.demand,
                            horizon_days=args.days), rb)
    base = whatif.replan(sc, rb, max_seconds=args.time_limit)
    print(f"base plan: {len(base.blocks)} blocks, "
          f"{len(base.unscheduled_task_ids)} deferred, "
          f"train cost {sum(b.train_cost for b in base.blocks):.0f}\n")

    builders = {
        "freight": lambda: whatif.add_freight(sc, n=args.n_freight),
        "crew": lambda: whatif.remove_crew(sc, args.crew_type, args.n_crew),
        "urgent": lambda: whatif.urgent_defect(sc, rb, args.section),
        "durations": lambda: whatif.inflate_durations(sc, args.factor),
    }
    for kind in (args.kinds or list(builders)):
        sc2, pert = builders[kind]()
        plan2 = whatif.replan(sc2, rb, hint=base, anchor=base,
                              max_seconds=args.time_limit)
        print(whatif.diff(base, plan2, pert.detail).summary())
        print()
    return 0


def cmd_export(args) -> int:
    from .export_static import ExportConfig, build, write

    cfg = ExportConfig(seed=args.seed, demand=args.demand, days=args.days,
                       ml=not args.no_ml, time_limit=args.time_limit,
                       out=Path(args.out))
    bundle = build(cfg)
    path = write(bundle, cfg.out)
    size = path.stat().st_size / 1024
    print(f"\nwrote {path}  ({size:.0f} KB)")
    print("build the UI in static mode to use it:")
    print("  cd ui && VITE_STATIC=1 npm run build")
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    ui = Path("ui/dist")
    if ui.is_dir():
        print(f"UI:  http://{args.host}:{args.port}/")
    else:
        print("ui/dist not built - run `cd ui && npm install && npm run build`,")
        print("or `npm run dev` in ui/ for the dev server on :5173")
    print(f"API: http://{args.host}:{args.port}/docs")
    uvicorn.run("sanchay.api.main:app", host=args.host, port=args.port,
                reload=args.reload, log_level="info")
    return 0


def cmd_ml(args) -> int:
    from .ml.duration import DEFAULT_LOG, train_and_report
    from .ml.value_experiment import report_multi, run_multi

    log = Path(args.log or DEFAULT_LOG)
    if not log.exists():
        print(f"no execution log at {log} - run `python -m sanchay gen` first")
        return 1
    print(f"training the duration model on {log}\n")
    model, rep = train_and_report(log, quantile=args.quantile)
    print(rep.summary())
    print("\ntop features")
    for name, gain in model.feature_importance(10):
        print(f"  {name:26s} {gain}")

    if args.risk:
        from .ml.risk import DEFAULT_HISTORY
        from .ml.risk import train_and_report as train_risk
        hist = Path(args.history or DEFAULT_HISTORY)
        if not hist.exists():
            print(f"\nno asset history at {hist} - run `python -m sanchay gen`")
            return 1
        print("\n" + "=" * 76)
        print(f"ASSET RISK MODEL  ({hist})\n")
        _, risk_rep = train_risk(hist)
        print(risk_rep.summary())

    if args.experiment:
        print("\n" + "=" * 76)
        print("DOES THE MODEL MAKE THE PLAN BETTER?\n")
        rb = Rulebook.load()
        buckets = run_multi(rb, model, seeds=tuple(range(1, args.scenarios + 1)),
                            time_limit=args.time_limit)
        print(report_multi(buckets))
    return 0


def cmd_ablate(args) -> int:
    from .eval.ablations import pareto_svg, run, summarise, write_csv

    seeds = tuple(range(1, args.seeds + 1))
    studies = tuple(args.studies) if args.studies else (
        "coordination", "pareto", "anytime", "screening", "durations")
    print(f"ablations: {', '.join(studies)} over {len(seeds)} seed(s), "
          f"{args.time_limit}s solver limit")
    t0 = time.time()
    rows = run(seeds=seeds, time_limit=args.time_limit, studies=studies)
    print(f"done in {time.time() - t0:.0f}s\n")
    print(summarise(rows))
    OUT.mkdir(exist_ok=True)
    write_csv(rows, OUT / "ablations.csv")
    if "pareto" in studies:
        (OUT / "pareto.svg").write_text(pareto_svg(rows))
        print(f"wrote {OUT / 'pareto.svg'}")
    print(f"wrote {OUT / 'ablations.csv'}")
    return 0


def cmd_bench(args) -> int:
    from .eval.harness import RunConfig, run, summarise, write_csv
    cfg = RunConfig(scenarios=args.scenarios,
                    demands=tuple(args.demands), time_limit=args.time_limit,
                    jobs=args.jobs)
    print(f"running {args.scenarios} seeds x {len(cfg.demands)} demand levels "
          f"x 4 methods, {args.time_limit}s solver limit, {args.jobs} parallel")
    t0 = time.time()
    rows = run(cfg)
    print(f"\ndone in {time.time() - t0:.0f}s\n")
    print(summarise(rows))
    OUT.mkdir(exist_ok=True)
    write_csv(rows, OUT / args.out)
    print(f"wrote {OUT / args.out}")
    return 0


# --- wiring ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sanchay", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--seed", type=int, default=1)
        sp.add_argument("--demand", choices=["low", "normal", "surge"], default="normal")
        sp.add_argument("--days", type=int, default=7, help="planning horizon")
        return sp

    g = common(sub.add_parser("gen", help="generate and save a scenario"))
    g.add_argument("--name", default="vijaypur_v1")
    g.add_argument("--log-rows", type=int, default=2500)
    g.add_argument("--history-months", type=int, default=24)
    g.set_defaults(func=cmd_gen)

    pl = common(sub.add_parser("plan", help="run every method and compare"))
    pl.add_argument("--time-limit", type=float, default=15.0)
    pl.add_argument("--html", default="compare.html", help="'' to skip the chart")
    pl.add_argument("--route", default="MAIN", choices=["MAIN", "BRANCH", "DIV"])
    pl.add_argument("--day", type=int, default=1, help="day to draw")
    pl.add_argument("-v", "--verbose", action="store_true", help="solver log")
    pl.add_argument("--ml", action="store_true",
                    help="plan to the duration model's P80 instead of nominal")
    pl.set_defaults(func=cmd_plan)

    ex = common(sub.add_parser("explain", help="why this block, why not that one"))
    ex.add_argument("--time-limit", type=float, default=15.0)
    ex.add_argument("--block", default=None, help="block id; default the largest coordinated one")
    ex.add_argument("--task", default=None)
    ex.add_argument("--alternatives", type=int, default=3)
    ex.set_defaults(func=cmd_explain)

    wi = common(sub.add_parser("whatif", help="perturb an assumption, re-optimise"))
    # Higher than you might expect on purpose: plan stability only behaves
    # when the *base* plan is already near-optimal. Given a weak base, the
    # re-solve finds improvements big enough to outweigh the anchor, and the
    # plan reshuffles - which looks like a bug and is really a short time limit.
    wi.add_argument("--time-limit", type=float, default=20.0)
    wi.add_argument("--kinds", nargs="*",
                    choices=["freight", "crew", "urgent", "durations"])
    wi.add_argument("--n-freight", type=int, default=10,
                    help="extra freight paths through the corridor window")
    wi.add_argument("--n-crew", type=int, default=1, help="gangs made unavailable")
    wi.add_argument("--crew-type", default="signal_team")
    wi.add_argument("--section", default="MAIN05")
    wi.add_argument("--factor", type=float, default=1.25)
    wi.set_defaults(func=cmd_whatif)

    ex = common(sub.add_parser(
        "export", help="bake a pre-solved demo bundle for the static site"))
    ex.add_argument("--time-limit", type=float, default=20.0)
    ex.add_argument("--no-ml", action="store_true")
    ex.add_argument("--out", default="ui/public/demo-bundle.json")
    ex.set_defaults(func=cmd_export)

    sv = sub.add_parser("serve", help="run the API and the web UI")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=cmd_serve)

    ml = sub.add_parser("ml", help="train the duration model and test its value")
    ml.add_argument("--log", default=None, help="execution log CSV")
    ml.add_argument("--quantile", type=float, default=0.8,
                    help="planning quantile; 0.5 plans to the median, which is "
                         "how half your blocks come to overrun")
    ml.add_argument("--experiment", action="store_true",
                    help="also run the plan-and-execute value experiment")
    ml.add_argument("--risk", action="store_true",
                    help="also train and report the asset risk model")
    ml.add_argument("--history", default=None, help="asset history CSV")
    ml.add_argument("--scenarios", type=int, default=5)
    ml.add_argument("--time-limit", type=float, default=12.0)
    ml.set_defaults(func=cmd_ml)

    ab = sub.add_parser("ablate", help="ablations and the Pareto frontier")
    ab.add_argument("--seeds", type=int, default=3)
    ab.add_argument("--time-limit", type=float, default=12.0)
    ab.add_argument("--studies", nargs="*",
                    choices=["coordination", "pareto", "anytime", "screening",
                             "durations"])
    ab.set_defaults(func=cmd_ablate)

    b = sub.add_parser("bench", help="the full benchmark")
    b.add_argument("--scenarios", type=int, default=10)
    b.add_argument("--demands", nargs="*", default=["low", "normal", "surge"])
    b.add_argument("--time-limit", type=float, default=15.0)
    b.add_argument("--jobs", type=int, default=4)
    b.add_argument("--out", default="benchmark.csv")
    b.set_defaults(func=cmd_bench)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

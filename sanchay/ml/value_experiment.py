"""Does the duration model actually make the plan better?

This is the experiment that justifies having an ML layer at all, and it is the
notebook to prioritise (docs/06-ml.md). Without it, "we use XGBoost" is a claim
about our toolkit, not a result.

The design:

  1. Build three plans from the same scenario, differing only in the duration
     each task is planned to - **nominal**, the model's **median**, and the
     model's **P80**.
  2. Simulate executing each plan using the *same* generating process that
     produced the training log (`gen.execution_log.true_duration`). Using a
     different process here would rig the experiment, and it is the first thing
     a sharp judge should ask about.
  3. Count what a controller actually cares about: how many blocks were handed
     back late, by how long, and what that cost in delayed trains.

The expected finding - and the sentence worth being able to say - is that
planning to the mean means roughly half your blocks overrun *by construction*,
and that the P80 buys most of that back for a modest amount of extra sanctioned
line time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..core.candidates import km_conflict
from ..core.models import Plan, Scenario
from ..core.rulebook import Rulebook
from ..core.timeutil import time_of_day
from ..core.traffic_cost import TrafficCostModel
from ..gen.execution_log import true_duration
from ..optimizer import whatif
from .duration import DurationModel, apply_predictions


@dataclass
class ExecutionOutcome:
    label: str
    n_blocks: int
    sanctioned_minutes: int
    blocks_overrun: int
    overrun_rate_pct: float
    total_overrun_min: int
    worst_overrun_min: int
    cascaded_delay_cost: float     # weighted train-minutes caused by overruns
    trains_delayed: int
    tasks_scheduled: int
    tasks_deferred: int

    def row(self) -> str:
        return (f"{self.label:22s}{self.n_blocks:8d}{self.sanctioned_minutes:12d}"
                f"{self.overrun_rate_pct:11.1f}{self.total_overrun_min:12d}"
                f"{self.worst_overrun_min:10d}{self.cascaded_delay_cost:14.0f}"
                f"{self.trains_delayed:9d}{self.tasks_deferred:10d}")


HEADER = (f"{'planned to':22s}{'blocks':>8s}{'sanction min':>12s}{'overrun %':>11s}"
          f"{'overrun min':>12s}{'worst':>10s}{'delay cost':>14s}"
          f"{'trains':>9s}{'deferred':>10s}")


def simulate_execution(plan: Plan, sc: Scenario, rb: Rulebook,
                       tc: TrafficCostModel, label: str,
                       seed: int = 4242, month: int = 7) -> ExecutionOutcome:
    """Run a plan against reality and see what actually happens.

    Inside each block we keep the planned order and re-run the sequencing with
    the *actual* durations: jobs far enough apart in km still run in parallel,
    jobs too close still have to queue. The block is handed back when the last
    one finishes.
    """
    rng = random.Random(seed)
    tasks = {t.id: t for t in sc.tasks}
    assets = {a.id: a for a in sc.assets}

    total_overrun = 0
    worst = 0
    overran = 0
    delay_cost = 0.0
    trains_delayed = 0

    for block in plan.blocks:
        members = [tasks[tid] for tid in block.task_ids]
        hour = time_of_day(block.start_min) // 60
        is_night = hour >= rb.policy.night_start_hour or hour < rb.policy.night_end_hour

        actual: dict[str, int] = {}
        for t in members:
            asset = assets.get(t.asset_id)
            dur, _ = true_duration(
                rng, nominal=t.nominal_duration_min, severity=t.severity,
                n_requires=len(rb[t.activity_type].requires),
                tasks_in_block=len(members), is_night=is_night,
                is_monsoon=month in (6, 7, 8, 9),
                access=rng.choices(["easy", "moderate", "hard"], [45, 40, 15])[0],
                band=rng.choices(["A", "B", "C"], [30, 45, 25])[0],
                asset_age=asset.age_years if asset else 12.0,
                failures_3y=asset.failures_3y if asset else 0)
            actual[t.id] = dur

        # replay the sequencing with real durations
        order = sorted(members, key=lambda t: block.task_times.get(
            t.id, (block.start_min, 0))[0])
        placed: list[tuple[object, int, int]] = []
        for t in order:
            start = block.start_min
            for other, os_, oe in placed:
                if km_conflict(t, other, rb):
                    start = max(start, oe)
                    
            placed.append((t, start, start + actual[t.id]))
        finished = max((e for _, _, e in placed), default=block.start_min)

        over = max(0, finished - block.end_min)
        if over > 0:
            overran += 1
            total_overrun += over
            worst = max(worst, over)
            # trains that should have run once the section was handed back
            for p in tc.affected(block.section_id, block.end_min, block.end_min + over):
                held = block.end_min + over - p.enter_min
                if held > 0:
                    weight = next((t.priority_weight for t in sc.trains
                                   if t.number == p.train_number), 2)
                    delay_cost += weight * held
                    trains_delayed += 1

    return ExecutionOutcome(
        label=label, n_blocks=len(plan.blocks),
        sanctioned_minutes=sum(b.duration_min for b in plan.blocks),
        blocks_overrun=overran,
        overrun_rate_pct=round(overran / len(plan.blocks) * 100, 1) if plan.blocks else 0.0,
        total_overrun_min=total_overrun, worst_overrun_min=worst,
        cascaded_delay_cost=round(delay_cost, 1), trains_delayed=trains_delayed,
        tasks_scheduled=len(plan.scheduled_task_ids),
        tasks_deferred=len(plan.unscheduled_task_ids),
    )


def run_experiment(sc: Scenario, rb: Rulebook, model: DurationModel,
                   time_limit: float = 15.0, seed: int = 4242
                   ) -> list[ExecutionOutcome]:
    """Plan three ways, execute all three against the same reality."""
    import copy

    tc = TrafficCostModel(sc.sections, sc.trains, sc.paths)
    outcomes = []
    variants = [
        ("nominal", None),
        ("model median", False),
        (f"model P{int(model.quantile * 100)}", True),
    ]
    for label, quantile in variants:
        world = copy.deepcopy(sc)
        if quantile is None:
            for t in world.tasks:
                t.predicted_duration_min = t.nominal_duration_min
        else:
            apply_predictions(world, rb, model, quantile=quantile)
        plan = whatif.replan(world, rb, max_seconds=time_limit)
        # execute against the same reality: same seed for every variant
        outcomes.append(simulate_execution(plan, world, rb, tc, label, seed=seed))
    return outcomes


def run_multi(rb: Rulebook, model: DurationModel, seeds=(1, 2, 3, 4, 5),
              time_limit: float = 12.0) -> dict[str, list[ExecutionOutcome]]:
    """The same experiment across several worlds, kept per-seed.

    One scenario is an anecdote. Results are returned unaggregated so the
    report can pair them: the same seed gives every variant the same world, and
    a win rate over paired runs says far more than a difference of means -
    especially here, where the means are noisy.
    """
    from ..gen.generate import GenConfig, generate

    buckets: dict[str, list[ExecutionOutcome]] = {}
    for seed in seeds:
        sc = generate(GenConfig(seed=seed), rb)
        for o in run_experiment(sc, rb, model, time_limit=time_limit, seed=4000 + seed):
            buckets.setdefault(o.label, []).append(o)
    return buckets


def report_multi(buckets: dict[str, list[ExecutionOutcome]]) -> str:
    """Paired report. Leads with the metric the model can actually claim."""
    labels = list(buckets)
    n = len(buckets[labels[0]])

    def mean(label, attr):
        return sum(getattr(o, attr) for o in buckets[label]) / n

    lines = [f"{n} scenarios, paired by seed", "", HEADER, "-" * len(HEADER)]
    for label in labels:
        lines.append(
            f"{label:22s}{mean(label, 'n_blocks'):8.0f}"
            f"{mean(label, 'sanctioned_minutes'):12.0f}"
            f"{mean(label, 'overrun_rate_pct'):11.1f}"
            f"{mean(label, 'total_overrun_min'):12.0f}"
            f"{mean(label, 'worst_overrun_min'):10.0f}"
            f"{mean(label, 'cascaded_delay_cost'):14.0f}"
            f"{mean(label, 'trains_delayed'):9.0f}"
            f"{mean(label, 'tasks_deferred'):10.0f}")

    base = labels[0]
    lines += ["", "Paired against planning to nominal durations:"]
    for label in labels[1:]:
        for attr, pretty in (("overrun_rate_pct", "overrun rate (pp)"),
                             ("total_overrun_min", "overrun minutes"),
                             ("worst_overrun_min", "worst overrun (min)"),
                             ("cascaded_delay_cost", "cascaded delay")):
            deltas = [getattr(a, attr) - getattr(b, attr)
                      for a, b in zip(buckets[label], buckets[base])]
            wins = sum(1 for d in deltas if d < 0)      # lower is better for all four
            lines.append(f"  {label:16s} {pretty:22s} "
                         f"{sum(deltas) / n:+9.1f}   better in {wins}/{n}")
        lines.append("")

    lines += [
        "READ THIS CAREFULLY BEFORE PUTTING IT ON A SLIDE.",
        "",
        "Overrun rate and overrun minutes are attributable to the duration model:",
        "they measure whether the sanctioned window was long enough for the work.",
        "",
        "Cascaded delay is NOT cleanly attributable. Each variant produces a",
        "different plan - different blocks, on different sections, at different",
        "times - so that number mixes duration accuracy with plan composition.",
        "Quote it as context, never as the model's effect.",
        "",
        "Simulated. Execution uses the same generating process that produced the",
        "training log, so the model is not evaluated on a rule it was handed.",
    ]
    return "\n".join(lines)


def report(outcomes: list[ExecutionOutcome]) -> str:
    lines = [HEADER, "-" * len(HEADER)]
    lines += [o.row() for o in outcomes]
    lines.append("")
    base = outcomes[0]
    lines.append("Change against planning to nominal durations "
                 "(negative = better, except sanctioned time):")
    for o in outcomes[1:]:
        lines.append(
            f"  {o.label:16s} overrun {o.total_overrun_min - base.total_overrun_min:+6d} min"
            f"   cascaded delay {o.cascaded_delay_cost - base.cascaded_delay_cost:+8.0f}"
            f"   sanctioned time {o.sanctioned_minutes - base.sanctioned_minutes:+6d} min")
    lines.append("")
    lines.append("Simulated. Execution uses the same generating process that produced")
    lines.append("the training log, so the model is not being evaluated on its own rule.")
    return "\n".join(lines)

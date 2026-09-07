"""Historical block execution records - the ML training set.

This closes the feedback loop in the concept note, and it is what makes the ML
layer honest (docs/06-ml.md). The primary model predicts how long a block will
*actually* take and whether it will overrun, and that prediction becomes the
duration the optimizer plans to. So the ML output changes the schedule, rather
than decorating it.

The generating process below is deliberately **not** the shape a gradient
boosting model would naturally take. It has:

  * a multiplicative structure with interaction terms,
  * a congestion effect (work is slower when more gangs share the block),
  * unobserved crew skill that the model never sees as a feature,
  * a heavy right tail from discrete disruption events (material, weather,
    late traffic clearance).

So the model has to *estimate* something rather than recall a rule. Report MAE
and a calibration curve, and use the P80 quantile - not the mean - as the
planning duration. Planning to the mean means half your blocks overrun by
construction.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path

from ..core.models import Scenario
from ..core.rulebook import Rulebook
from ..core.timeutil import MINUTES_PER_DAY, time_of_day

BASE_EFFICIENCY = 0.60

OVERRUN_REASONS = ["late_start", "material", "weather", "crew",
                   "traffic_clearance", "scope"]
FIELDS = [
    "block_id", "task_id", "activity_type", "dept", "asset_type", "section_id",
    "line_type", "km", "asset_age_years", "days_since_maintenance", "severity",
    "crew_type", "crew_experience_band", "tasks_in_block", "block_permits",
    "start_hour", "is_night", "month", "is_monsoon", "access_difficulty",
    "nominal_duration_min", "actual_duration_min", "overran", "overrun_min",
    "overrun_reason",
]


@dataclass
class LogConfig:
    seed: int = 99
    n_records: int = 2500


def _sample(rng: random.Random, sc: Scenario, rb: Rulebook, idx: int) -> dict:
    task = rng.choice(sc.tasks)
    act = rb[task.activity_type]
    section = sc.section(task.section_id)
    asset = next((a for a in sc.assets if a.id == task.asset_id), None)

    tasks_in_block = rng.choices([1, 2, 3, 4, 5], [30, 28, 22, 13, 7])[0]
    start_min = rng.randrange(0, MINUTES_PER_DAY, 15)
    hour = time_of_day(start_min) // 60
    is_night = hour >= rb.policy.night_start_hour or hour < rb.policy.night_end_hour
    month = rng.randint(1, 12)
    is_monsoon = month in (6, 7, 8, 9)
    access = rng.choices(["easy", "moderate", "hard"], [45, 40, 15])[0]
    band = rng.choices(["A", "B", "C"], [30, 45, 25])[0]

    # --- the generating process (never shown to the model) ---------------
    # The rulebook's nominal duration is what a requisition *asks for*, and a
    # requisition already carries contingency. So a typical job comes in under
    # nominal; an overrun is what happens when the factors below eat through
    # that contingency. BASE_EFFICIENCY sets where the centre of the
    # distribution sits, and is calibrated to an overrun rate in the high
    # twenties - the shape a real execution log tends to have.
    skill = {"A": 0.88, "B": 1.0, "C": 1.16}[band] * rng.gauss(1.0, 0.05)
    factor = BASE_EFFICIENCY * skill
    factor *= 1.0 + 0.055 * (tasks_in_block - 1)          # congestion
    factor *= 1.13 if is_night else 1.0
    factor *= 1.17 if is_monsoon else 1.0
    factor *= {"easy": 1.0, "moderate": 1.09, "hard": 1.24}[access]
    if asset is not None:
        factor *= 1.0 + 0.004 * asset.age_years
        factor *= 1.0 + 0.10 * math.log1p(asset.failures_3y)
    factor *= {"routine": 0.97, "important": 1.0, "critical": 1.08}[task.severity]
    factor *= 1.08 if len(act.requires) >= 2 else 1.0     # more permits, more setup

    # heavy right tail: a discrete disruption on roughly one block in eight
    reason = ""
    if rng.random() < 0.13:
        reason = rng.choice(OVERRUN_REASONS)
        factor *= rng.uniform(1.25, 2.1)

    nominal = task.nominal_duration_min
    actual = max(15, int(round(nominal * factor * rng.gauss(1.0, 0.07) / 5) * 5))
    overran = actual > nominal
    if overran and not reason:
        reason = rng.choice(["late_start", "scope", "traffic_clearance"])

    return {
        "block_id": f"H{idx:06d}", "task_id": task.id,
        "activity_type": task.activity_type, "dept": task.dept,
        "asset_type": asset.asset_type if asset else "unknown",
        "section_id": task.section_id, "line_type": section.line_type,
        "km": round(task.km_from, 2),
        "asset_age_years": asset.age_years if asset else 0.0,
        "days_since_maintenance": asset.days_since_maintenance if asset else 0,
        "severity": task.severity, "crew_type": task.crew_type,
        "crew_experience_band": band, "tasks_in_block": tasks_in_block,
        "block_permits": "|".join(sorted(act.requires)),
        "start_hour": hour, "is_night": int(is_night), "month": month,
        "is_monsoon": int(is_monsoon), "access_difficulty": access,
        "nominal_duration_min": nominal, "actual_duration_min": actual,
        "overran": int(overran), "overrun_min": max(0, actual - nominal),
        "overrun_reason": reason if overran else "",
    }


def generate_log(sc: Scenario, rb: Rulebook, cfg: LogConfig | None = None) -> list[dict]:
    cfg = cfg or LogConfig()
    rng = random.Random(cfg.seed)
    return [_sample(rng, sc, rb, i + 1) for i in range(cfg.n_records)]


def write_log(rows: list[dict], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path

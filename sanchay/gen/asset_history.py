"""Asset condition history — the training set for the risk model.

Twenty-four monthly snapshots of every asset, with the label "did this asset
develop a reportable defect in the following 30 days?".

The generating process is a Weibull hazard in maintenance-interval units,
modulated by tonnage, age and failure history — and by two variables the model
never sees: drainage quality and formation condition. Those unobserved
confounders are the point. Without them a gradient-boosting model would simply
recover the arithmetic we used to make the labels, and "our model achieves
0.99 AUC" would mean nothing at all.

Maintenance is endogenous, as it is in reality: a defect triggers attention,
which resets days-since-maintenance, which lowers the hazard. So the model has
to learn from a history shaped by the very interventions it is meant to inform.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path

from ..core.models import Scenario

FIELDS = [
    "asset_id", "month_index", "asset_type", "dept", "section_id", "line_type",
    "age_years", "days_since_maintenance", "maintenance_interval_days",
    "overdue_ratio", "annual_gmt", "criticality", "failures_to_date",
    "months_since_last_defect", "season", "is_monsoon",
    "defect_within_30d",
]
#: Never features. Recorded so the notebook can show what the model was up
#: against, and so a reviewer can confirm they were withheld.
HIDDEN = ["drainage_quality", "formation_condition", "true_hazard"]


@dataclass
class HistoryConfig:
    seed: int = 77
    months: int = 24


def _hazard(*, overdue_ratio: float, age: float, gmt: float, failures: int,
            drainage: float, formation: float, is_monsoon: bool) -> float:
    """The truth. Not shown to the model, and not the shape it will fit."""
    shape, scale = 2.1, 1.35
    base = 1.0 - math.exp(-((max(0.0, overdue_ratio) / scale) ** shape))
    wear = 1.0 + 0.018 * age + 0.0040 * gmt
    history = 1.0 + 0.13 * failures
    # the unobserved half: poor drainage and a weak formation dominate in the
    # monsoon, which is exactly the interaction a days-since-maintenance rule
    # cannot express
    condition = (2.0 - drainage) * (2.0 - formation)
    seasonal = 1.0 + (0.55 * condition if is_monsoon else 0.10 * condition)
    return min(0.97, base * wear * history * seasonal * 0.30)


def generate_history(sc: Scenario, cfg: HistoryConfig | None = None) -> list[dict]:
    cfg = cfg or HistoryConfig()
    rng = random.Random(cfg.seed)
    sections = {s.id: s for s in sc.sections}
    rows: list[dict] = []

    for asset in sc.assets:
        drainage = rng.betavariate(5, 2)        # 0 poor .. 1 good
        formation = rng.betavariate(4, 2)
        days = asset.days_since_maintenance
        age = asset.age_years
        failures = asset.failures_3y
        months_since_defect = rng.randrange(1, 36)

        for m in range(cfg.months):
            month_of_year = (m % 12) + 1
            is_monsoon = month_of_year in (6, 7, 8, 9)
            overdue = days / max(1, asset.maintenance_interval_days)
            h = _hazard(overdue_ratio=overdue, age=age, gmt=asset.annual_gmt,
                        failures=failures, drainage=drainage,
                        formation=formation, is_monsoon=is_monsoon)
            defect = rng.random() < h

            rows.append({
                "asset_id": asset.id, "month_index": m,
                "asset_type": asset.asset_type, "dept": asset.dept,
                "section_id": asset.section_id,
                "line_type": sections[asset.section_id].line_type,
                "age_years": round(age, 2), "days_since_maintenance": days,
                "maintenance_interval_days": asset.maintenance_interval_days,
                "overdue_ratio": round(overdue, 3),
                "annual_gmt": asset.annual_gmt, "criticality": asset.criticality,
                "failures_to_date": failures,
                "months_since_last_defect": months_since_defect,
                "season": ["winter", "summer", "monsoon", "post_monsoon"][
                    (month_of_year - 1) // 3],
                "is_monsoon": int(is_monsoon),
                "defect_within_30d": int(defect),
                # withheld from the model, kept for the notebook
                "drainage_quality": round(drainage, 3),
                "formation_condition": round(formation, 3),
                "true_hazard": round(h, 4),
            })

            # advance one month. A defect draws attention, which resets the
            # clock - maintenance is endogenous, exactly as in reality.
            age += 1 / 12
            if defect:
                failures += 1
                months_since_defect = 0
                days = rng.randrange(0, 20)
            else:
                months_since_defect += 1
                days += 30
                # routine attention when well overdue, but not reliably
                if days > asset.maintenance_interval_days * 1.4 and rng.random() < 0.45:
                    days = rng.randrange(0, 25)
    return rows


def write_history(rows: list[dict], path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS + HIDDEN)
        writer.writeheader()
        writer.writerows(rows)
    return path

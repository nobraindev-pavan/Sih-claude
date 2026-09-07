"""Builds the synthetic Vijaypur division.

Everything is seeded, so the same seed always produces byte-identical data.
That matters more than it sounds: every benchmark number the team ever quotes
must come from the same world, and a teammate reproducing a result must get
the same numbers.

Nothing here claims to be real railway data. It is *schema-compatible* with
TMS / SMMS / TDMS / COA so that swapping in a real feed is a connector change
(see docs/04-architecture.md), and it is shaped to be operationally plausible.

The division, fixed once (docs/03-scope.md):

    MAIN     180 km, double line, electrified, 12 block stations, 11 sections
    BRANCH    60 km, single line,  off the junction at KM 88, 4 sections
    DIVERSION a parallel route around the KM 103-120 section

The single-line branch is deliberate: there, any block is a total closure, so
the optimizer faces a genuinely hard trade-off rather than a comfortable one.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..core.models import (Asset, Crew, Scenario, Section, Station, Task, Train,
                           TrainPath, Window)
from ..core.rulebook import Rulebook
from ..core.timeutil import MINUTES_PER_DAY, at, overlaps

# --- the fixed geography -----------------------------------------------------
MAIN_STATIONS = [
    ("VJP", "Vijaypur", 0.0), ("KHD", "Khandoli", 16.0), ("BRW", "Barwani", 32.0),
    ("NGD", "Nagdah", 47.0), ("STP", "Satpura Road", 61.0), ("DHM", "Dholpura", 74.0),
    ("MKJ", "Makarjeri Jn", 88.0), ("AMB", "Ambori", 103.0), ("RSL", "Rasulpur", 120.0),
    ("TKD", "Tikadih", 136.0), ("BHN", "Bhanwargarh", 151.0), ("SGR", "Sagarwada", 180.0),
]
BRANCH_STATIONS = [
    ("MKJ", "Makarjeri Jn", 0.0), ("PPL", "Pipaliya", 14.0), ("GHT", "Ghatera", 29.0),
    ("SLW", "Salewara", 44.0), ("KNJ", "Kanjari", 60.0),
]
#: Trains per day by class, and the effective section speed each makes good.
TRAIN_MIX = [
    ("VB", 2, 92), ("RAJ", 4, 88), ("MEX", 24, 66), ("PASS", 12, 48),
    ("MEMU", 8, 45), ("FRT", 46, 38),
]
#: Corridor windows, per Railway Board policy: three hours daily, built into
#: the working timetable. Staggered so the whole division is not shut at once.
CORRIDOR = {"MAIN": (10, 13), "BRANCH": (13, 16), "DIV": (10, 13)}

ASSET_SPEC = [
    # (dept, asset_type, per_km, interval_days, base_criticality)
    ("ENG", "track_segment", 2.0, 180, 3),   # 500 m granularity
    ("ENG", "level_crossing", 0.05, 120, 3),
    ("ENG", "bridge", 0.03, 365, 5),
    ("SNT", "signal", 0.40, 150, 4),
    ("SNT", "point_machine", 0.15, 120, 5),
    ("SNT", "track_circuit", 0.50, 180, 4),
    ("TRD", "ohe_section", 0.40, 200, 4),
    ("TRD", "ohe_mast", 1.50, 365, 2),
]
#: Which activities are plausible on which asset type.
ACTIVITY_FOR_ASSET = {
    "track_segment": ["ENG_TAMPING", "ENG_RAIL_RENEWAL", "ENG_WELD_REPAIR",
                      "ENG_BALLAST_SCREENING"],
    "level_crossing": ["ENG_LC_MAINTENANCE"],
    "bridge": ["ENG_BRIDGE_INSPECTION"],
    "signal": ["SNT_SIGNAL_TESTING", "SNT_CABLE_WORK"],
    "point_machine": ["SNT_POINT_OVERHAUL"],
    "track_circuit": ["SNT_TRACK_CIRCUIT", "SNT_AXLE_COUNTER"],
    "ohe_section": ["TRD_OHE_INSULATOR", "TRD_CONTACT_WIRE", "TRD_ISOLATOR_SERVICE",
                    "TRD_TENSIONING"],
    "ohe_mast": ["TRD_MAST_REPAIR"],
}
CREWS_PER_TYPE = {
    "track_gang": 4, "track_machine": 2, "bridge_gang": 1,
    "signal_team": 4, "ohe_team": 3, "ohe_tower_car": 2,
}
DEMAND_LEVELS = {"low": 0.6, "normal": 1.0, "surge": 1.5}


@dataclass
class GenConfig:
    seed: int = 1
    horizon_days: int = 7
    demand: str = "normal"
    tasks_per_week: int = 180
    name: str = "vijaypur"


# --- network -----------------------------------------------------------------

def _build_network() -> tuple[list[Station], list[Section]]:
    stations = [Station(c, n, km, "MAIN") for c, n, km in MAIN_STATIONS]
    sections: list[Section] = []
    for i in range(len(MAIN_STATIONS) - 1):
        a, b = MAIN_STATIONS[i], MAIN_STATIONS[i + 1]
        sections.append(Section(f"MAIN{i + 1:02d}", a[0], b[0], a[2], b[2],
                                "double", max_speed_kmph=110))

    stations += [Station(c, n, km, "BRANCH") for c, n, km in BRANCH_STATIONS[1:]]
    for i in range(len(BRANCH_STATIONS) - 1):
        a, b = BRANCH_STATIONS[i], BRANCH_STATIONS[i + 1]
        sections.append(Section(f"BRCH{i + 1:02d}", a[0], b[0], a[2], b[2],
                                "single", max_speed_kmph=75))

    # A parallel route around MAIN08 (AMB 103 -> RSL 120). Blocking both at once
    # severs the corridor, so the optimizer is forbidden from doing it.
    sections.append(Section("DIV01", "AMB", "RSL", 103.0, 120.0, "single",
                            max_speed_kmph=75, diversion_for="MAIN08"))
    return stations, sections


def _corridor_windows(sections: list[Section], horizon_days: int) -> list[Window]:
    out: list[Window] = []
    for sec in sections:
        group = "BRANCH" if sec.id.startswith("BRCH") else (
            "DIV" if sec.id.startswith("DIV") else "MAIN")
        h0, h1 = CORRIDOR[group]
        for d in range(horizon_days):
            out.append(Window(sec.id, at(d, h0), at(d, h1), "corridor"))
    return out


# --- timetable ---------------------------------------------------------------

def _path_for(rng: random.Random, train: Train, dep_min: int, speed: float,
              sections: list[Section], route: str) -> list[TrainPath]:
    """Walk a train through its route, section by section, from a departure."""
    on_route = [s for s in sections
                if (s.id.startswith("BRCH") if route == "BRANCH" else s.id.startswith("MAIN"))]
    on_route.sort(key=lambda s: s.km_from, reverse=(train.direction == "UP"))
    t = dep_min
    paths: list[TrainPath] = []
    for sec in on_route:
        run = sec.length_km / speed * 60.0
        dwell = rng.choice([0, 0, 1, 2]) if train.train_class in ("VB", "RAJ") else \
            rng.choice([1, 2, 3, 5])
        enter, exit_ = int(t), int(t + run)
        paths.append(TrainPath(train.number, sec.id, enter, exit_))
        t = exit_ + dwell
    return paths


def _build_timetable(rng: random.Random, sections: list[Section],
                     corridor: list[Window], horizon_days: int
                     ) -> tuple[list[Train], list[TrainPath], int]:
    """Generate train paths that respect the corridor windows.

    Rejection sampling: draw a departure, walk the path, and keep it only if it
    fouls no corridor window. That is what "the timetable is built around the
    corridor block" means in practice, and it is why corridor windows cost
    almost nothing in train disruption.
    """
    by_section: dict[str, list[Window]] = {}
    for w in corridor:
        by_section.setdefault(w.section_id, []).append(w)

    trains: list[Train] = []
    paths: list[TrainPath] = []
    dropped = 0
    n = 0
    for day in range(horizon_days):
        for cls, per_day, speed in TRAIN_MIX:
            for _ in range(per_day):
                n += 1
                direction = rng.choice(["UP", "DN"])
                # roughly a fifth of services work the branch
                route = "BRANCH" if (cls in ("PASS", "MEMU", "FRT") and rng.random() < 0.22) \
                    else "MAIN"
                train = Train(f"{12000 + n}", cls, direction)
                placed = False
                for _try in range(80):
                    dep = at(day, 0) + rng.randrange(0, MINUTES_PER_DAY, 5)
                    jitter = speed * rng.uniform(0.92, 1.08)
                    cand = _path_for(rng, train, dep, jitter, sections, route)
                    if any(p.exit_min >= horizon_days * MINUTES_PER_DAY for p in cand):
                        continue
                    clash = any(
                        overlaps(p.enter_min, p.exit_min, w.start_min, w.end_min)
                        for p in cand for w in by_section.get(p.section_id, []))
                    if not clash:
                        trains.append(train)
                        paths.extend(cand)
                        placed = True
                        break
                if not placed:
                    dropped += 1
    return trains, paths, dropped


# --- assets ------------------------------------------------------------------

def _build_assets(rng: random.Random, sections: list[Section]) -> list[Asset]:
    assets: list[Asset] = []
    n = 0
    for sec in sections:
        gmt = rng.uniform(30, 70) if sec.line_type == "double" else rng.uniform(8, 22)
        for dept, atype, per_km, interval, crit in ASSET_SPEC:
            count = max(1, int(sec.length_km * per_km))
            for _ in range(count):
                n += 1
                lo = min(sec.km_from, sec.km_to)
                km = round(lo + rng.random() * sec.length_km, 2)
                span = 0.5 if atype == "track_segment" else 0.0
                age = rng.uniform(0.5, 32)
                assets.append(Asset(
                    id=f"{atype[:3].upper()}{n:05d}",
                    dept=dept, asset_type=atype, section_id=sec.id,
                    km_from=km, km_to=round(km + span, 2),
                    age_years=round(age, 1),
                    days_since_maintenance=rng.randrange(5, int(interval * 2.2)),
                    maintenance_interval_days=interval,
                    criticality=min(5, max(1, crit + rng.choice([-1, 0, 0, 1]))),
                    annual_gmt=round(gmt, 1),
                    failures_3y=rng.choices([0, 1, 2, 3, 5], [55, 25, 12, 6, 2])[0],
                ))
    return assets


def true_hazard(a: Asset) -> float:
    """The *generating* process for asset condition. Not a formula the ML sees.

    Deliberately not the shape the model will be fitted with (docs/06-ml.md):
    a Weibull-style hazard in maintenance-interval units, modulated by tonnage
    and failure history. Seat 3 fits gradient boosting to samples of this and
    reports calibration - which is a real result, because the model has to
    estimate this rather than recall it.
    """
    overdue = a.days_since_maintenance / max(1, a.maintenance_interval_days)
    shape, scale = 2.1, 1.35
    base = 1.0 - math.exp(-((overdue / scale) ** shape))
    wear = 1.0 + 0.020 * a.age_years + 0.0045 * a.annual_gmt
    history = 1.0 + 0.14 * a.failures_3y
    return min(0.985, base * wear * history * 0.55)


# --- demand ------------------------------------------------------------------

def _priority(task: Task, risk: float, crit: int, horizon_min: int) -> float:
    """The transparent priority policy from the concept note.

    This is a *rule*, not a learned model, and that is a virtue here: a Sr. DEN
    can inspect and argue with these weights. Calibrate them by asking a domain
    contact to rank twenty sample tasks (docs/06-ml.md).
    """
    urgency = max(0.0, 1.0 - task.due_min / max(1, horizon_min))
    overdue = 1.0 if task.due_min < horizon_min * 0.35 else 0.0
    return round(
        2.5 * task.severity_rank
        + 3.0 * urgency
        + 4.0 * risk
        + 1.2 * crit
        + 1.5 * overdue, 3)


def _build_tasks(rng: random.Random, assets: list[Asset], rb: Rulebook,
                 cfg: GenConfig, horizon_min: int) -> list[Task]:
    n_tasks = int(cfg.tasks_per_week * DEMAND_LEVELS[cfg.demand]
                  * cfg.horizon_days / 7)
    # Sample the assets most likely to need attention, but not deterministically -
    # real backlogs contain routine work on healthy assets too.
    scored = [(a, true_hazard(a)) for a in assets]
    weights = [0.15 + h for _, h in scored]
    picked: list[tuple[Asset, float]] = []
    seen: set[str] = set()
    guard = 0
    while len(picked) < n_tasks and guard < n_tasks * 40:
        guard += 1
        a, h = rng.choices(scored, weights=weights, k=1)[0]
        if a.id in seen:
            continue
        seen.add(a.id)
        picked.append((a, h))

    tasks: list[Task] = []
    counters = {"ENG": 0, "SNT": 0, "TRD": 0}
    for a, hazard in picked:
        codes = ACTIVITY_FOR_ASSET[a.asset_type]
        code = rng.choice(codes)
        act = rb[code]
        counters[a.dept] += 1
        tid = f"{a.dept}-{counters[a.dept]:03d}"

        if hazard > 0.7:
            severity = rng.choices(["critical", "important"], [7, 3])[0]
        elif hazard > 0.4:
            severity = rng.choices(["critical", "important", "routine"], [2, 6, 2])[0]
        else:
            severity = rng.choices(["important", "routine"], [3, 7])[0]

        # Critical work is due sooner. Due dates land on a day boundary, which
        # is how a real requisition carries them.
        span = {"critical": (1, 3), "important": (2, 6), "routine": (4, 9)}[severity]
        due_day = min(cfg.horizon_days, rng.randint(*span))
        due = min(horizon_min, at(due_day, 0))

        dur = int(act.nominal_duration_min * rng.uniform(0.85, 1.2) / 15) * 15
        dur = min(dur, rb.policy.max_block_duration_min)  # policy caps block length
        risk = round(min(0.99, max(0.01, hazard * rng.uniform(0.85, 1.15))), 3)

        t = Task(
            id=tid, dept=a.dept, activity_type=code, asset_id=a.id,
            section_id=a.section_id, km_from=a.km_from, km_to=a.km_to,
            severity=severity, raised_min=0, due_min=due,
            nominal_duration_min=max(30, dur), crew_type=act.crew_type,
            risk_score=risk,
        )
        t.priority_score = _priority(t, risk, a.criticality, horizon_min)
        tasks.append(t)
    tasks.sort(key=lambda t: t.id)
    return tasks


def _build_crews(rng: random.Random) -> list[Crew]:
    dept_of = {"track_gang": "ENG", "track_machine": "ENG", "bridge_gang": "ENG",
               "signal_team": "SNT", "ohe_team": "TRD", "ohe_tower_car": "TRD"}
    crews: list[Crew] = []
    for ctype, count in CREWS_PER_TYPE.items():
        for i in range(count):
            crews.append(Crew(f"{ctype.upper()}-{i + 1}", dept_of[ctype], ctype,
                              home_km=round(rng.uniform(0, 180), 1)))
    return crews


# --- entry point -------------------------------------------------------------

def generate(cfg: GenConfig, rulebook: Rulebook | None = None) -> Scenario:
    rb = rulebook or Rulebook.load()
    rng = random.Random(cfg.seed)
    horizon_min = cfg.horizon_days * MINUTES_PER_DAY

    stations, sections = _build_network()
    corridor = _corridor_windows(sections, cfg.horizon_days)
    trains, paths, dropped = _build_timetable(rng, sections, corridor, cfg.horizon_days)
    if dropped > len(trains) * 0.05:
        raise RuntimeError(
            f"timetable generation dropped {dropped} trains - the corridor windows "
            "are probably too wide for the traffic mix")
    assets = _build_assets(rng, sections)
    tasks = _build_tasks(rng, assets, rb, cfg, horizon_min)
    crews = _build_crews(rng)

    return Scenario(
        name=f"{cfg.name}-s{cfg.seed}-{cfg.demand}", seed=cfg.seed,
        horizon_days=cfg.horizon_days, stations=stations, sections=sections,
        assets=assets, tasks=tasks, crews=crews, trains=trains, paths=paths,
        corridor_windows=corridor,
    )

"""The data model. This is the contract; change it deliberately.

Field names deliberately echo what a real TMS / SMMS / TDMS / BDMS record
carries, so that mapping to the real systems is a rename rather than a
redesign. See docs/04-architecture.md.

Plain dataclasses, not pydantic: fewer concepts for a team learning Python,
and nothing here needs runtime validation that a test can't do better.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Dept = Literal["ENG", "SNT", "TRD"]
Permit = Literal["traffic_block", "power_block", "disconnection"]
LineType = Literal["single", "double"]

#: Train classes, highest operational priority first. The weight is what a
#: minute of delay to that class costs in the objective. Freight is low for
#: punctuality but high for revenue - offer this as a tunable if a judge asks.
TRAIN_PRIORITY = {
    "VB": 10,    # Vande Bharat
    "RAJ": 10,   # Rajdhani / Shatabdi class
    "MEX": 6,    # Mail / Express
    "PASS": 3,   # Passenger
    "MEMU": 3,   # MEMU / EMU
    "FRT": 2,    # Freight
}

SEVERITY_RANK = {"routine": 1, "important": 2, "critical": 3}


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Station:
    code: str
    name: str
    km: float
    line: str            # which route this station sits on ("MAIN", "BRANCH")
    is_block_station: bool = True


@dataclass(frozen=True)
class Section:
    """A block section: the stretch between two consecutive block stations.

    Only one train may occupy it at a time under the Absolute Block System,
    which is why it is the atomic unit of our scheduling problem - a block is
    always granted *on a block section*.
    """
    id: str
    from_station: str
    to_station: str
    km_from: float
    km_to: float
    line_type: LineType
    electrified: bool = True
    max_speed_kmph: int = 110
    #: Section id this one can divert traffic to. If both are blocked at the
    #: same time the route is severed, so the optimizer forbids that.
    diversion_for: str | None = None

    @property
    def length_km(self) -> float:
        return abs(self.km_to - self.km_from)

    def covers(self, km_from: float, km_to: float) -> bool:
        lo, hi = min(self.km_from, self.km_to), max(self.km_from, self.km_to)
        return lo <= min(km_from, km_to) and max(km_from, km_to) <= hi


# --------------------------------------------------------------------------
# Assets and work
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Asset:
    id: str
    dept: Dept
    asset_type: str
    section_id: str
    km_from: float
    km_to: float          # equal to km_from for point assets (signals, points)
    age_years: float
    days_since_maintenance: int
    maintenance_interval_days: int
    criticality: int       # 1..5
    annual_gmt: float      # gross million tonnes carried - traffic importance
    failures_3y: int


@dataclass(frozen=True)
class ActivityType:
    """One row of the safety rulebook. Loaded from data/rulebook.yaml."""
    code: str
    dept: Dept
    name: str
    requires: frozenset[str]      # permits this work cannot proceed without
    forbids: frozenset[str]       # permits that make this work impossible
    nominal_duration_min: int
    min_separation_m: int         # clearance from any other worksite
    crew_type: str


@dataclass
class Task:
    """A maintenance demand. The unified form of a TMS/SMMS/TDMS requisition."""
    id: str
    dept: Dept
    activity_type: str
    asset_id: str
    section_id: str
    km_from: float
    km_to: float
    severity: str                 # routine | important | critical
    raised_min: int
    due_min: int                  # hard deadline, in horizon minutes
    nominal_duration_min: int
    crew_type: str
    #: What the optimizer actually plans to. Set from the ML model when one is
    #: trained (docs/06-ml.md); falls back to nominal until then.
    predicted_duration_min: int = 0
    overrun_probability: float = 0.0
    risk_score: float = 0.0       # P(defect within 30 days), 0..1
    priority_score: float = 0.0
    crew_id: str | None = None

    def __post_init__(self) -> None:
        if not self.predicted_duration_min:
            self.predicted_duration_min = self.nominal_duration_min

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK[self.severity]


@dataclass(frozen=True)
class Crew:
    id: str
    dept: Dept
    crew_type: str
    home_km: float
    travel_speed_kmph: float = 30.0

    def travel_minutes(self, km_a: float, km_b: float) -> int:
        return int(abs(km_a - km_b) / self.travel_speed_kmph * 60)


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Train:
    number: str
    train_class: str
    direction: str        # "UP" (km high->low) or "DN" (km low->high)

    @property
    def priority_weight(self) -> int:
        return TRAIN_PRIORITY[self.train_class]


@dataclass(frozen=True)
class TrainPath:
    """One train's occupation of one section, in horizon minutes."""
    train_number: str
    section_id: str
    enter_min: int
    exit_min: int


@dataclass(frozen=True)
class Window:
    """A candidate period during which a block *could* be taken on a section.

    Two sources. 'corridor' windows come from the Railway Board policy that
    keeps every section vacant for three hours daily - the timetable is built
    around them, so they cost almost no train disruption. 'gap' windows are
    naturally occurring lulls found in the timetable.
    """
    section_id: str
    start_min: int
    end_min: int
    source: Literal["corridor", "gap"]

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min


@dataclass(frozen=True)
class CandidateBlock:
    """A block the optimizer may choose to open. The decision object.

    This is the key modelling choice (docs/05-optimizer.md): we enumerate
    candidate blocks and let the solver pick which to open, rather than
    indexing decisions by (task, time, section). It makes "minimise the number
    of separate blocks" literally `sum(open[b])`, and coordination emerges
    from the setup cost rather than from a hand-written merge rule.
    """
    id: str
    section_id: str
    start_min: int
    end_min: int
    window_source: str
    #: Precomputed outside the solver - this is what keeps solving fast.
    train_cost: float
    trains_affected: tuple[str, ...]

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

@dataclass
class Block:
    """A block in a produced plan, with the tasks assigned into it."""
    id: str
    section_id: str
    start_min: int
    end_min: int
    permits: frozenset[str]
    task_ids: list[str]
    trains_affected: list[str]
    train_cost: float
    window_source: str = "gap"
    #: task_id -> (start_min, end_min) inside the block
    task_times: dict[str, tuple[int, int]] = field(default_factory=dict)
    status: str = "proposed"

    @property
    def duration_min(self) -> int:
        return self.end_min - self.start_min

    @property
    def departments(self) -> list[str]:
        return sorted({tid.split("-")[0] for tid in self.task_ids})

    @property
    def is_coordinated(self) -> bool:
        """True when more than one department shares this block."""
        return len(self.departments) > 1


@dataclass
class Plan:
    """What a scheduler produces. All three methods return one of these."""
    method: str
    blocks: list[Block]
    unscheduled_task_ids: list[str]
    solver_status: str = "n/a"
    objective_value: float = 0.0
    best_bound: float = 0.0
    solve_seconds: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)

    @property
    def scheduled_task_ids(self) -> list[str]:
        return [tid for b in self.blocks for tid in b.task_ids]

    @property
    def gap_pct(self) -> float:
        """Optimality gap. 0.0 means proven optimal - say this number out loud."""
        if self.objective_value == 0:
            return 0.0
        return abs(self.objective_value - self.best_bound) / abs(self.objective_value) * 100


@dataclass
class Scenario:
    """One complete world: network, assets, demand and timetable."""
    name: str
    seed: int
    horizon_days: int
    stations: list[Station]
    sections: list[Section]
    assets: list[Asset]
    tasks: list[Task]
    crews: list[Crew]
    trains: list[Train]
    paths: list[TrainPath]
    corridor_windows: list[Window]

    @property
    def horizon_min(self) -> int:
        return self.horizon_days * 24 * 60

    def section(self, sid: str) -> Section:
        return self._by_id("sections", sid)

    def task(self, tid: str) -> Task:
        return self._by_id("tasks", tid)

    def train(self, num: str) -> Train:
        for t in self.trains:
            if t.number == num:
                return t
        raise KeyError(num)

    def _by_id(self, coll: str, key: str):
        cache_attr = f"_cache_{coll}"
        if not hasattr(self, cache_attr):
            object.__setattr__(self, cache_attr, {o.id: o for o in getattr(self, coll)})
        return getattr(self, cache_attr)[key]

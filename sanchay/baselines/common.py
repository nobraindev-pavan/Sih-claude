"""Shared greedy machinery for the baseline schedulers.

Both baselines must respect *every* constraint the optimizer respects - the
same rulebook, the same crew counts, the same section exclusivity, the same
candidate blocks. A baseline that cheats invalidates the whole comparison, and
a judge will look for exactly that (docs/07-evaluation.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.candidates import km_conflict
from ..core.models import Block, CandidateBlock, Scenario, Task
from ..core.rulebook import ALL_PERMITS, Rulebook
from ..core.timeutil import overlaps
from ..optimizer.cpsat import MOBILISE_MIN


@dataclass
class ResourceLedger:
    """Tracks what is already committed, so a greedy grant stays legal."""
    sc: Scenario
    rb: Rulebook
    #: section_id -> list of (start, end) already blocked
    section_busy: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    #: crew_type -> list of (start, end) occupied, one entry per committed task
    crew_busy: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    _diversion: dict[str, str] = field(default_factory=dict)
    _crew_cap: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for s in self.sc.sections:
            if s.diversion_for:
                self._diversion[s.id] = s.diversion_for
                self._diversion[s.diversion_for] = s.id
        for c in self.sc.crews:
            self._crew_cap[c.crew_type] = self._crew_cap.get(c.crew_type, 0) + 1

    def section_free(self, section_id: str, start: int, end: int) -> bool:
        for sid in (section_id, self._diversion.get(section_id)):
            if sid is None:
                continue
            for bs, be in self.section_busy.get(sid, []):
                if overlaps(start, end, bs, be):
                    return False
        return True

    def crew_free(self, crew_type: str, start: int, end: int) -> bool:
        # Default 0, not 1: no gangs of this type means no work of this type.
        cap = self._crew_cap.get(crew_type, 0)
        busy = sum(1 for bs, be in self.crew_busy.get(crew_type, [])
                   if overlaps(start, end + MOBILISE_MIN, bs, be))
        return busy < cap

    def commit_block(self, section_id: str, start: int, end: int) -> None:
        self.section_busy.setdefault(section_id, []).append((start, end))

    def commit_task(self, task: Task, start: int, end: int) -> None:
        self.crew_busy.setdefault(task.crew_type, []).append(
            (start, end + MOBILISE_MIN))


def place_in_block(task: Task, block: CandidateBlock, placed: list[tuple[Task, int, int]],
                   rb: Rulebook, ledger: ResourceLedger) -> tuple[int, int] | None:
    """Earliest legal slot for `task` inside `block`, or None.

    Legal means: the block's permit set stays workable for everything in it, no
    explicitly incompatible activity is present, no km-conflicting worksite is
    active at the same moment, and a crew of the right type is free.
    """
    codes = [t.activity_type for t, _, _ in placed]
    ok, _ = rb.block_is_legal(codes + [task.activity_type])
    if not ok:
        return None

    dur = task.predicted_duration_min
    if dur > block.duration_min:
        return None

    conflicts = [(s, e) for t, s, e in placed if km_conflict(t, task, rb)]
    candidates = sorted({block.start_min} | {e for _, e in conflicts})
    for start in candidates:
        end = start + dur
        if end > block.end_min:
            break
        if any(overlaps(start, end, cs, ce) for cs, ce in conflicts):
            continue
        if not ledger.crew_free(task.crew_type, start, end):
            continue
        return start, end
    return None


def shrink_to_fit(cand: CandidateBlock, placed: list[tuple[Task, int, int]],
                  by_key: dict[tuple[str, int], list[CandidateBlock]]) -> CandidateBlock:
    """Swap a candidate for the shortest one on the same section and start that
    still contains all the placed work.

    A controller does not requisition four hours to do one hour of work. Without
    this the greedy schedulers would be penalised for a choice no real planner
    would make, and the comparison against the solver would flatter it.
    """
    need_end = max(e for _, _, e in placed)
    options = [b for b in by_key.get((cand.section_id, cand.start_min), [])
               if b.end_min >= need_end]
    return min(options, key=lambda b: b.duration_min) if options else cand


def finalise(blocks_raw: list[tuple[CandidateBlock, list[tuple[Task, int, int]]]],
             rb: Rulebook, method: str) -> list[Block]:
    """Turn greedy placements into Block records.

    The block spans the whole window that was sanctioned, not just the minutes
    worked. That is the railway semantics: traffic is regulated around the
    requisitioned period, so finishing early does not un-delay the trains. Every
    method is charged the same way.
    """
    out: list[Block] = []
    for cand, placed in blocks_raw:
        if not placed:
            continue
        start, end = cand.start_min, cand.end_min
        permits = rb.block_permits([t.activity_type for t, _, _ in placed])
        out.append(Block(
            id=cand.id, section_id=cand.section_id, start_min=start, end_min=end,
            permits=frozenset(p for p in ALL_PERMITS if p in permits),
            task_ids=sorted(t.id for t, _, _ in placed),
            trains_affected=list(cand.trains_affected), train_cost=cand.train_cost,
            window_source=cand.window_source,
            task_times={t.id: (s, e) for t, s, e in placed}))
    out.sort(key=lambda b: (b.start_min, b.section_id))
    return out

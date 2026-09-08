"""What a block costs in train disruption.

The concept note left this as a weight with no formula, which will not survive
contact with a railway judge - it is the number an operator actually cares
about. Here it is, concretely:

    cost = sum over affected trains of  priority_weight(class) x delay_minutes

On a **double line** a block can usually be worked with single-line working:
trains still pass, at reduced capacity, taking a fixed penalty.

On a **single line** the section is completely closed. A train that would have
entered during the block is detained until it reopens, so its delay depends on
how early it arrives - and a long block on a single line is genuinely
expensive. That asymmetry is what makes the branch line interesting.

This is precomputed once per candidate block, outside the solver. That is the
single change that makes the model solve in seconds rather than minutes
(docs/05-optimizer.md).
"""

from __future__ import annotations

from .models import Section, Train, TrainPath
from .timeutil import overlaps

#: Delay taken by a train worked past a block under single-line working.
SINGLE_LINE_WORKING_DELAY_MIN = 12
#: A train detained longer than this would be regulated away or cancelled;
#: we charge the cancellation cost instead of an unbounded delay.
CANCELLATION_THRESHOLD_MIN = 120
CANCELLATION_COST_MIN = 180


class TrafficCostModel:
    def __init__(self, sections: list[Section], trains: list[Train],
                 paths: list[TrainPath]) -> None:
        self._section = {s.id: s for s in sections}
        self._weight = {t.number: t.priority_weight for t in trains}
        self._class = {t.number: t.train_class for t in trains}
        self._by_section: dict[str, list[TrainPath]] = {}
        for p in paths:
            self._by_section.setdefault(p.section_id, []).append(p)
        for v in self._by_section.values():
            v.sort(key=lambda p: p.enter_min)

    def affected(self, section_id: str, start: int, end: int) -> list[TrainPath]:
        return [p for p in self._by_section.get(section_id, [])
                if overlaps(p.enter_min, p.exit_min, start, end)]

    def cost(self, section_id: str, start: int, end: int
             ) -> tuple[float, tuple[str, ...]]:
        """(weighted cost in train-minutes, the trains affected)."""
        sec = self._section[section_id]
        hit = self.affected(section_id, start, end)
        total = 0.0
        for p in hit:
            w = self._weight[p.train_number]
            if sec.line_type == "double":
                delay = SINGLE_LINE_WORKING_DELAY_MIN
            else:
                detained = max(0, end - p.enter_min)
                delay = (CANCELLATION_COST_MIN
                         if detained > CANCELLATION_THRESHOLD_MIN else detained)
            total += w * delay
        return round(total, 1), tuple(p.train_number for p in hit)

    def breakdown(self, section_id: str, start: int, end: int) -> dict[str, int]:
        """Trains affected by class - for the explanation panel."""
        out: dict[str, int] = {}
        for p in self.affected(section_id, start, end):
            cls = self._class[p.train_number]
            out[cls] = out.get(cls, 0) + 1
        return dict(sorted(out.items()))

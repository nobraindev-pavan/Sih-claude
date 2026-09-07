"""Finding the periods when a block could be taken.

Two sources, and the distinction matters for the pitch:

  corridor  The Railway Board's mandated three-hour daily maintenance window.
            The working timetable is built around it, so almost no train is
            scheduled through it and its disruption cost is near zero. This is
            the window the optimizer should want.

  gap       A naturally occurring lull found in the timetable. Usable, but a
            block here competes with real train paths.

A block also needs time either side to be protected and returned. We reserve
PROTECTION_MIN at each end, so a "free" interval must be longer than the work
it can hold.
"""

from __future__ import annotations

from .models import Section, TrainPath, Window
from .timeutil import MINUTES_PER_DAY

#: Minutes needed to protect the block before work starts and to clear the
#: section before traffic resumes. Not work time.
PROTECTION_MIN = 10
#: A gap shorter than this cannot hold any useful work, so we discard it.
MIN_GAP_MIN = 45


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    out = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def _subtract(base: tuple[int, int], cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """base minus each cut, returning whatever survives."""
    pieces = [base]
    for cs, ce in cuts:
        nxt: list[tuple[int, int]] = []
        for ps, pe in pieces:
            if ce <= ps or cs >= pe:
                nxt.append((ps, pe))
                continue
            if ps < cs:
                nxt.append((ps, cs))
            if ce < pe:
                nxt.append((ce, pe))
        pieces = nxt
    return pieces


def occupied_intervals(paths: list[TrainPath], section_id: str) -> list[tuple[int, int]]:
    """When the section is in use, padded by the protection time at each end."""
    raw = [(p.enter_min - PROTECTION_MIN, p.exit_min + PROTECTION_MIN)
           for p in paths if p.section_id == section_id]
    return _merge(raw)


def generate_windows(sections: list[Section], paths: list[TrainPath],
                     corridor: list[Window], horizon_days: int,
                     min_gap_min: int = MIN_GAP_MIN) -> list[Window]:
    """Every window on every section: corridor windows plus timetable gaps."""
    horizon = horizon_days * MINUTES_PER_DAY
    corridor_by_section: dict[str, list[Window]] = {}
    for w in corridor:
        corridor_by_section.setdefault(w.section_id, []).append(w)

    windows: list[Window] = list(corridor)
    for sec in sections:
        busy = occupied_intervals(paths, sec.id)
        cuts = [(w.start_min, w.end_min) for w in corridor_by_section.get(sec.id, [])]

        free: list[tuple[int, int]] = []
        cursor = 0
        for s, e in busy:
            if s > cursor:
                free.append((cursor, min(s, horizon)))
            cursor = max(cursor, e)
        if cursor < horizon:
            free.append((cursor, horizon))

        for lo, hi in free:
            for gs, ge in _subtract((lo, hi), cuts):
                usable = ge - gs - 2 * PROTECTION_MIN
                if usable >= min_gap_min:
                    windows.append(Window(sec.id, gs + PROTECTION_MIN,
                                          ge - PROTECTION_MIN, "gap"))
    windows.sort(key=lambda w: (w.section_id, w.start_min))
    return windows

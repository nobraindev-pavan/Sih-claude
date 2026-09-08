"""Time handling.

One rule, and everything downstream depends on it: **all times are integer
minutes measured from the start of the planning horizon**. Day 0 at 00:00 is
minute 0. There are no datetimes anywhere inside the solver.

Why: CP-SAT works on integers, and mixing datetime objects into the model is
the single most common way scheduling code becomes unreadable. Convert at the
edges (loading and display), never in the middle.
"""

from __future__ import annotations

MINUTES_PER_DAY = 24 * 60
GRANULARITY_MIN = 15  # the planning grid; nothing is scheduled off it


def day_of(minute: int) -> int:
    """Which day of the horizon a minute falls on. Day 0 is the first day."""
    return minute // MINUTES_PER_DAY


def time_of_day(minute: int) -> int:
    """Minutes past midnight, ignoring which day it is."""
    return minute % MINUTES_PER_DAY


def at(day: int, hour: int, minute: int = 0) -> int:
    """Build a horizon minute from a day and a wall-clock time."""
    return day * MINUTES_PER_DAY + hour * 60 + minute


def hhmm(minute: int) -> str:
    """Render a horizon minute as 'HH:MM' (no day). For labels and logs."""
    tod = time_of_day(minute)
    return f"{tod // 60:02d}:{tod % 60:02d}"


def stamp(minute: int) -> str:
    """Render a horizon minute as 'D2 14:30'. For anything a human reads."""
    return f"D{day_of(minute)} {hhmm(minute)}"


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """True when two half-open intervals [start, end) share any minute.

    Touching intervals do not overlap: [0, 60) and [60, 120) are fine
    back-to-back, which is what we want for consecutive blocks.
    """
    return a_start < b_end and b_start < a_end


def round_up(minute: int, grid: int = GRANULARITY_MIN) -> int:
    return ((minute + grid - 1) // grid) * grid


def round_down(minute: int, grid: int = GRANULARITY_MIN) -> int:
    return (minute // grid) * grid

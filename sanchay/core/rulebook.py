"""Loads and queries the safety rulebook (data/rulebook.yaml).

Everything this module returns is a hard constraint for the optimizer. There
is deliberately no way to express "prefer not to" here - if a rule belongs in
the objective it does not belong in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import ActivityType

ALL_PERMITS = ("traffic_block", "power_block", "disconnection")
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "rulebook.yaml"


@dataclass(frozen=True)
class Policy:
    max_block_duration_min: int = 240
    min_block_duration_min: int = 45
    night_start_hour: int = 23
    night_end_hour: int = 5


class Rulebook:
    def __init__(self, activities: dict[str, ActivityType],
                 incompatible: set[frozenset[str]], policy: Policy) -> None:
        self.activities = activities
        self._incompatible = incompatible
        self.policy = policy

    # -- loading ----------------------------------------------------------
    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "Rulebook":
        raw = yaml.safe_load(Path(path).read_text())
        activities: dict[str, ActivityType] = {}
        for code, spec in raw["activity_types"].items():
            requires = frozenset(spec.get("requires", []))
            forbids = frozenset(spec.get("forbids", []))
            unknown = (requires | forbids) - set(ALL_PERMITS)
            if unknown:
                raise ValueError(f"{code}: unknown permit(s) {sorted(unknown)}")
            if requires & forbids:
                raise ValueError(f"{code}: requires and forbids the same permit")
            activities[code] = ActivityType(
                code=code,
                dept=spec["dept"],
                name=spec["name"],
                requires=requires,
                forbids=forbids,
                nominal_duration_min=int(spec["nominal_duration_min"]),
                min_separation_m=int(spec["min_separation_m"]),
                crew_type=spec["crew_type"],
            )
        incompatible = set()
        for a, b in raw.get("incompatible_pairs", []):
            for code in (a, b):
                if code not in activities:
                    raise ValueError(f"incompatible_pairs names unknown activity {code}")
            incompatible.add(frozenset((a, b)))
        return cls(activities, incompatible, Policy(**raw.get("policy", {})))

    # -- queries ----------------------------------------------------------
    def __getitem__(self, code: str) -> ActivityType:
        return self.activities[code]

    def codes_for(self, dept: str) -> list[str]:
        return [c for c, a in self.activities.items() if a.dept == dept]

    def pair_incompatible(self, code_a: str, code_b: str) -> bool:
        """Explicitly listed as unable to share a block."""
        return frozenset((code_a, code_b)) in self._incompatible

    def permit_conflict(self, code_a: str, code_b: str) -> str | None:
        """The permit that makes these two unable to share a block, if any.

        One requires what the other forbids. This is why an OHE insulator
        replacement (needs the power off) and a signal aspect test (needs it
        on) can never be in the same block, however close they are in km.
        """
        a, b = self.activities[code_a], self.activities[code_b]
        clash = (a.requires & b.forbids) | (b.requires & a.forbids)
        return sorted(clash)[0] if clash else None

    def can_share_block(self, code_a: str, code_b: str) -> tuple[bool, str]:
        """(allowed, reason). The reason is shown to planners, so keep it plain."""
        if self.pair_incompatible(code_a, code_b):
            return False, f"{code_a} and {code_b} are listed as mutually unsafe"
        permit = self.permit_conflict(code_a, code_b)
        if permit:
            return False, f"one requires {permit} and the other cannot work under it"
        return True, "compatible"

    def separation_m(self, code_a: str, code_b: str) -> int:
        """Clearance two worksites must keep. The stricter of the two rules."""
        return max(self.activities[code_a].min_separation_m,
                   self.activities[code_b].min_separation_m)

    def block_permits(self, codes) -> frozenset[str]:
        """The permit set a block must hold to run all of these activities."""
        out: set[str] = set()
        for c in codes:
            out |= self.activities[c].requires
        return frozenset(out)

    def block_is_legal(self, codes) -> tuple[bool, str]:
        """Whether this exact set of activities may occupy one block."""
        codes = list(codes)
        permits = self.block_permits(codes)
        for c in codes:
            bad = self.activities[c].forbids & permits
            if bad:
                return False, f"{c} cannot work while the block holds {sorted(bad)[0]}"
        for i, a in enumerate(codes):
            for b in codes[i + 1:]:
                ok, why = self.can_share_block(a, b)
                if not ok:
                    return False, why
        return True, "legal"

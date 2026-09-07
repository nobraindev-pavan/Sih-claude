"""Reading and writing a scenario as CSV.

Plain CSV on purpose. A teammate can open these in a spreadsheet, a mentor can
see exactly what the system is being fed, and the field names are the ones the
connectors map to. SQLite arrives in Phase 2 when it earns its keep
(docs/03-scope.md) - not before.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

from .models import (Asset, Crew, Scenario, Section, Station, Task, Train,
                     TrainPath, Window)

TABLES = {
    "stations.csv": Station, "sections.csv": Section, "assets.csv": Asset,
    "tasks.csv": Task, "crews.csv": Crew, "trains.csv": Train,
    "train_paths.csv": TrainPath, "corridor_windows.csv": Window,
}
_ATTR = {"stations.csv": "stations", "sections.csv": "sections", "assets.csv": "assets",
         "tasks.csv": "tasks", "crews.csv": "crews", "trains.csv": "trains",
         "train_paths.csv": "paths", "corridor_windows.csv": "corridor_windows"}


def _coerce(cls: type, row: dict[str, str]) -> Any:
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        raw = row.get(f.name, "")
        if raw == "" and f.name in ("diversion_for", "crew_id"):
            kwargs[f.name] = None
            continue
        t = f.type if not isinstance(f.type, str) else f.type
        name = t if isinstance(t, str) else getattr(t, "__name__", "str")
        if "int" in name and "str" not in name:
            kwargs[f.name] = int(float(raw))
        elif "float" in name:
            kwargs[f.name] = float(raw)
        elif "bool" in name:
            kwargs[f.name] = raw in ("True", "true", "1")
        else:
            kwargs[f.name] = raw
    return cls(**kwargs)


def save_scenario(sc: Scenario, out_dir: Path | str) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for filename, cls in TABLES.items():
        rows = getattr(sc, _ATTR[filename])
        path = out / filename
        with path.open("w", newline="") as fh:
            names = [f.name for f in fields(cls)]
            writer = csv.DictWriter(fh, fieldnames=names)
            writer.writeheader()
            for obj in rows:
                d = asdict(obj) if is_dataclass(obj) else dict(obj)
                writer.writerow({k: ("" if d.get(k) is None else d.get(k)) for k in names})
    (out / "META.txt").write_text(
        f"name={sc.name}\nseed={sc.seed}\nhorizon_days={sc.horizon_days}\n"
        "SIMULATED DATA. Schema-compatible with TMS / SMMS / TDMS / COA; not\n"
        "derived from any real railway system. See docs/field-mapping.md.\n")
    return out


def load_scenario(in_dir: Path | str) -> Scenario:
    src = Path(in_dir)
    meta = dict(line.split("=", 1) for line in
                (src / "META.txt").read_text().splitlines() if "=" in line)
    data: dict[str, list] = {}
    for filename, cls in TABLES.items():
        with (src / filename).open() as fh:
            data[_ATTR[filename]] = [_coerce(cls, row) for row in csv.DictReader(fh)]
    return Scenario(name=meta.get("name", src.name), seed=int(meta.get("seed", 0)),
                    horizon_days=int(meta.get("horizon_days", 7)), **data)

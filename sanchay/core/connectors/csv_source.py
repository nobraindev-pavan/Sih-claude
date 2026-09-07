"""CSV connectors - the implementation that exists today."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ..models import Scenario
from .base import AssetRecord, TaskRecord

SOURCE_FOR_DEPT = {"ENG": "TMS", "SNT": "SMMS", "TRD": "TDMS"}


@dataclass
class CsvMaintenanceConnector:
    """Reads one department's backlog from a scenario directory.

    Standing in for TMS (Engineering), SMMS (S&T) or TDMS (Traction
    Distribution) depending on `dept`.
    """
    scenario_dir: Path
    dept: str

    @property
    def name(self) -> str:
        return SOURCE_FOR_DEPT.get(self.dept, "CSV")

    def fetch_tasks(self) -> list[TaskRecord]:
        out: list[TaskRecord] = []
        with (Path(self.scenario_dir) / "tasks.csv").open() as fh:
            for row in csv.DictReader(fh):
                if row["dept"] != self.dept:
                    continue
                out.append(TaskRecord(
                    source=self.name, external_id=row["id"], dept=row["dept"],
                    activity=row["activity_type"], asset_ref=row["asset_id"],
                    location=f"KM {float(row['km_from']):.3f}-{float(row['km_to']):.3f}",
                    severity=row["severity"], due=row["due_min"],
                    duration_min=row["nominal_duration_min"], raw=dict(row)))
        return out

    def fetch_assets(self) -> list[AssetRecord]:
        out: list[AssetRecord] = []
        with (Path(self.scenario_dir) / "assets.csv").open() as fh:
            for row in csv.DictReader(fh):
                if row["dept"] != self.dept:
                    continue
                out.append(AssetRecord(
                    source=self.name, external_id=row["id"], dept=row["dept"],
                    asset_type=row["asset_type"],
                    location=f"KM {float(row['km_from']):.3f}",
                    last_maintenance=row["days_since_maintenance"], raw=dict(row)))
        return out


@dataclass
class CsvOperationsConnector:
    """Standing in for COA - the Control Office Application, which is where the
    train chart and section throughput actually live."""
    scenario_dir: Path
    name: str = "COA"

    def fetch_paths(self) -> list[dict]:
        with (Path(self.scenario_dir) / "train_paths.csv").open() as fh:
            return list(csv.DictReader(fh))

    def fetch_corridor_windows(self) -> list[dict]:
        with (Path(self.scenario_dir) / "corridor_windows.csv").open() as fh:
            return list(csv.DictReader(fh))


def all_maintenance_connectors(scenario_dir: Path) -> list[CsvMaintenanceConnector]:
    return [CsvMaintenanceConnector(scenario_dir, d) for d in ("ENG", "SNT", "TRD")]

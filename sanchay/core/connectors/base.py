"""The connector interface. Every source system implements this shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TaskRecord:
    """A maintenance demand as it arrives from a source system, before
    normalisation. Deliberately stringly-typed: real feeds are messy, and the
    normalisation step is where we admit that."""
    source: str            # TMS | SMMS | TDMS | BDMS
    external_id: str
    dept: str
    activity: str
    asset_ref: str
    location: str          # e.g. "KM 120.500-125.000" or a station/asset code
    severity: str
    due: str
    duration_min: str
    raw: dict


@dataclass(frozen=True)
class AssetRecord:
    source: str
    external_id: str
    dept: str
    asset_type: str
    location: str
    last_maintenance: str
    raw: dict


@runtime_checkable
class SourceConnector(Protocol):
    """What every maintenance source must provide."""
    name: str

    def fetch_tasks(self) -> list[TaskRecord]: ...
    def fetch_assets(self) -> list[AssetRecord]: ...

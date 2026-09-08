"""Deployment-shaped connectors. Not implemented, and honest about it.

These exist so that "how would this connect to the real systems?" has a bounded
answer with a visible amount of work behind it, instead of a hand-wave. Each
docstring records the mapping from our unified schema to the fields a real
record carries. Confirm every one of these against the actual system before
claiming it - the names below are our best reading of published material, not
verified integration specifications.

Do NOT implement these against a live system without written authorisation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import AssetRecord, TaskRecord

NOT_IMPLEMENTED = (
    "Deployment connector. Requires an authorised endpoint and credentials that "
    "a student prototype does not and should not have. The CSV connector is the "
    "working implementation; this class documents the shape of the real one.")


@dataclass
class BdmsApiConnector:
    """Block & Disconnection Management System (CRIS).

    BDMS is where block demands are actually raised, routed and tracked across
    traffic, power and disconnection blocks. It is our natural integration
    point: we consume the same requisitions and return a proposed allocation
    for a human to sanction.

    Mapping (our field <- their concept):
        task.id                <- block demand / requisition number
        task.dept              <- demanding department
        task.section_id        <- block section (from/to block station)
        task.km_from/km_to     <- chainage of the worksite
        task.activity_type     <- nature of work
        task.nominal_duration  <- block duration sought
        task.due_min           <- target/latest date for the work
        block.permits          <- demand type: traffic / power / disconnection
        block.status           <- demand status: raised, sanctioned, cancelled
    """
    base_url: str
    division: str
    name: str = "BDMS"

    def fetch_tasks(self) -> list[TaskRecord]:
        raise NotImplementedError(NOT_IMPLEMENTED)

    def fetch_assets(self) -> list[AssetRecord]:
        raise NotImplementedError(NOT_IMPLEMENTED)


@dataclass
class CoaApiConnector:
    """Control Office Application (CRIS) - the source of the train chart.

    Mapping:
        train.number           <- train number
        train.train_class      <- train type, which sets operating priority
        train_path.section_id  <- block section
        train_path.enter/exit  <- scheduled or actual times at either end
        corridor_window        <- the maintenance block built into the WTT
    """
    base_url: str
    division: str
    name: str = "COA"

    def fetch_paths(self) -> list[dict]:
        raise NotImplementedError(NOT_IMPLEMENTED)


@dataclass
class TmsApiConnector:
    """Track Management System - Engineering assets, inspections and defects.

    Mapping:
        asset.id                     <- track asset / segment identifier
        asset.km_from/km_to          <- chainage
        asset.annual_gmt             <- gross million tonnes carried
        asset.days_since_maintenance <- last attention date
        task.severity                <- defect classification
    """
    base_url: str
    division: str
    name: str = "TMS"

    def fetch_tasks(self) -> list[TaskRecord]:
        raise NotImplementedError(NOT_IMPLEMENTED)

    def fetch_assets(self) -> list[AssetRecord]:
        raise NotImplementedError(NOT_IMPLEMENTED)

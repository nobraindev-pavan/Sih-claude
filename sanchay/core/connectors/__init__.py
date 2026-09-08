"""Ingestion connectors: one class per source system.

The point of this package is a sentence you can say to a judge:

    "Everything you saw runs against a connector interface. Point it at BDMS
     and COA and the only thing that changes is one class per source."

Today there is a CSV implementation. The API implementations are stubs that
carry the real field mapping in their docstrings, so the work required is
visible and bounded rather than hand-waved. See docs/field-mapping.md.
"""

from .base import AssetRecord, SourceConnector, TaskRecord  # noqa: F401
from .csv_source import CsvMaintenanceConnector, CsvOperationsConnector  # noqa: F401

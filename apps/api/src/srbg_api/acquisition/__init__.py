"""Acquisition contracts shared by API and Worker orchestration."""

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    DocumentParser,
    FetchResult,
    SourceAdapter,
    SourceCheckpoint,
    SourceConnector,
)

__all__ = [
    "DiscoveryBatch",
    "DiscoveryRecord",
    "DocumentParser",
    "FetchResult",
    "SourceAdapter",
    "SourceCheckpoint",
    "SourceConnector",
]

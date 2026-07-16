"""Acquisition contracts shared by API and Worker orchestration."""

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    DocumentParser,
    DocumentVersion,
    ExecutionDomain,
    FetchResult,
    RawObject,
    SourceAdapter,
    SourceCheckpoint,
    SourceConnector,
)

__all__ = [
    "DiscoveryBatch",
    "DiscoveryRecord",
    "DocumentParser",
    "DocumentVersion",
    "ExecutionDomain",
    "FetchResult",
    "RawObject",
    "SourceAdapter",
    "SourceCheckpoint",
    "SourceConnector",
]

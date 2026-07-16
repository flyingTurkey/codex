from uuid import UUID

from srbg_api.retention.service import RetentionCandidate, RetentionService


class Collaborators:
    def __init__(self, *, confirmed: bool = True) -> None:
        self.confirmed = confirmed
        self.calls: list[str] = []

    async def invalidate_for_retention(self, document_version_id: UUID, *, reason: str) -> None:
        del document_version_id, reason
        self.calls.append("invalidate")

    async def retention_invalidation_confirmed(self, document_version_id: UUID) -> bool:
        del document_version_id
        self.calls.append("confirm")
        return self.confirmed

    async def erase(self, object_key: str) -> None:
        del object_key
        self.calls.append("erase")

    async def record(
        self,
        candidate: RetentionCandidate,
        *,
        status: str,
        publication_invalidated: bool,
        erasure_method: str | None,
    ) -> None:
        del candidate, publication_invalidated, erasure_method
        self.calls.append(f"record:{status}")


def _candidate(**changes: object) -> RetentionCandidate:
    values: dict[str, object] = {
        "execution_id": UUID("019b1600-0000-7000-8000-000000000201"),
        "source_id": UUID("019b1600-0000-7000-8000-000000000202"),
        "raw_object_id": UUID("019b1600-0000-7000-8000-000000000203"),
        "document_version_id": UUID("019b1600-0000-7000-8000-000000000204"),
        "policy_version_id": UUID("019b1600-0000-7000-8000-000000000205"),
        "object_key": "sha256/aa/" + "a" * 64,
        "content_sha256": "a" * 64,
        "byte_size": 10,
        "mime": "text/html",
        "legal_hold_active": False,
        "unique_published_evidence": True,
        "reason": "approved retention expiry",
    }
    values.update(changes)
    return RetentionCandidate(**values)  # type: ignore[arg-type]


async def test_unique_published_evidence_is_invalidated_and_confirmed_before_erasure() -> None:
    collaborators = Collaborators()
    service = RetentionService(
        publication=collaborators,
        eraser=collaborators,
        recorder=collaborators,
    )
    assert await service.execute(_candidate()) == "ERASED"
    assert collaborators.calls == ["invalidate", "confirm", "erase", "record:ERASED"]


async def test_legal_hold_and_unconfirmed_projection_stop_erasure() -> None:
    held = Collaborators()
    held_service = RetentionService(publication=held, eraser=held, recorder=held)
    assert await held_service.execute(_candidate(legal_hold_active=True)) == "BLOCKED_LEGAL_HOLD"
    assert "erase" not in held.calls

    pending = Collaborators(confirmed=False)
    pending_service = RetentionService(publication=pending, eraser=pending, recorder=pending)
    assert await pending_service.execute(_candidate()) == "INVALIDATING"
    assert "erase" not in pending.calls

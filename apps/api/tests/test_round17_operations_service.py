from __future__ import annotations

from base64 import b64encode
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from srbg_api.operations.service import (
    _bounded_active_seconds,
    _eventization_manifest_is_trusted,
    _gold_agreement_metrics,
    _gold_annotation_evidence_is_authoritative,
    _gold_manifest_sha256,
    _gold_release_sources_match_window,
    _gold_sample_is_authoritative,
    _round17_leo_actor_is_attested,
    _round17_schedule_attestation_blockers,
    _round17_schedule_values_from_authority,
    _round17_schedule_write_blockers,
    _round17_snapshot_blockers,
    _source_supports_gold_domain,
)
from srbg_contracts import GoldSampleKind


def test_gold_manifest_hash_is_canonical_and_order_independent() -> None:
    left = [
        {"task_id": "b", "decision_code": "DISTINCT", "annotation_id": "2"},
        {"task_id": "a", "decision_code": "SAME", "annotation_id": "1"},
    ]
    right = list(reversed(left))

    assert _gold_manifest_sha256(left) == _gold_manifest_sha256(right)
    assert len(_gold_manifest_sha256(left)) == 64


def test_operator_session_never_counts_more_than_fifteen_minutes_without_heartbeat() -> None:
    started = datetime(2026, 7, 16, 1, 0, tzinfo=UTC)

    assert _bounded_active_seconds(started, started + timedelta(minutes=7)) == 420
    assert _bounded_active_seconds(started, started + timedelta(hours=3)) == 900


def test_operator_task_service_uses_database_lifecycle_functions() -> None:
    service = Path("apps/api/src/srbg_api/operations/service.py").read_text(
        encoding="utf-8"
    )
    create = service.split("async def create_operator_task", 1)[1].split(
        "async def complete_operator_task", 1
    )[0]
    complete = service.split("async def complete_operator_task", 1)[1].split(
        "async def start_work_session", 1
    )[0]
    start = service.split("async def start_work_session", 1)[1].split(
        "async def heartbeat_work_session", 1
    )[0]

    assert "exactly one controlled yinzi operator binding" in create
    assert "INSERT INTO round17_operator_task" in create
    assert "complete_round17_operator_task" in complete
    assert "start_round17_operator_task" in start
    assert "INSERT INTO round17_operator_work_session" not in start


def test_gold_agreement_is_recomputed_from_blind_labels() -> None:
    perfect = [
        {"task_id": "a", "signature": "SUPPORTED"},
        {"task_id": "a", "signature": "SUPPORTED"},
        {"task_id": "b", "signature": "NOT_SUPPORTED"},
        {"task_id": "b", "signature": "NOT_SUPPORTED"},
    ]
    disputed = [*perfect[:-1], {"task_id": "b", "signature": "SUPPORTED"}]

    assert _gold_agreement_metrics(perfect) == {
        "double_labeled_count": 2,
        "raw_agreement": 1.0,
        "coefficient_name": "GWET_AC1",
        "coefficient": 1.0,
    }
    assert _gold_agreement_metrics(disputed)["raw_agreement"] == 0.5
    assert _gold_agreement_metrics(disputed)["coefficient"] < 1.0


class _ScalarConnection:
    def __init__(self, result: int | bool) -> None:
        self.result = result
        self.sql = ""
        self.parameters: dict[str, object] = {}

    async def scalar(self, statement: object, parameters: dict[str, object]) -> int | bool:
        self.sql = str(statement)
        self.parameters = parameters
        return self.result


async def test_gold_document_sample_requires_current_production_non_fixture_source() -> None:
    source_id = UUID("019b1700-0000-7000-8000-000000000001")
    document_ids = (
        UUID("019b1700-0000-7000-8000-000000000002"),
        UUID("019b1700-0000-7000-8000-000000000003"),
    )
    connection = _ScalarConnection(2)

    assert await _gold_sample_is_authoritative(
        connection,
        sample_kind=GoldSampleKind.PAIR,
        identities=document_ids,
        source_id=source_id,
    )
    assert "document.admission_fixture=false" in connection.sql
    assert "version.execution_domain='PRODUCTION'" in connection.sql
    assert "document.source_id=:source" in connection.sql
    assert connection.parameters["expected_count"] == 2

    connection.result = 1
    assert not await _gold_sample_is_authoritative(
        connection,
        sample_kind=GoldSampleKind.PAIR,
        identities=document_ids,
        source_id=source_id,
    )


async def test_gold_event_sample_requires_confirmed_production_source_evidence() -> None:
    connection = _ScalarConnection(True)

    assert await _gold_sample_is_authoritative(
        connection,
        sample_kind=GoldSampleKind.EVENT,
        identities=(UUID("019b1700-0000-7000-8000-000000000004"),),
        source_id=UUID("019b1700-0000-7000-8000-000000000001"),
    )
    assert "event.confirmation_status='CONFIRMED'" in connection.sql
    assert "FROM event_item" in connection.sql
    assert "document.admission_fixture=false" in connection.sql
    assert "version.execution_domain='PRODUCTION'" in connection.sql
    assert "NOT EXISTS" in connection.sql
    assert "contaminated_membership.event_id=event.id" in connection.sql
    assert "contaminated_document.admission_fixture" in connection.sql
    assert "contaminated_version.execution_domain<>'PRODUCTION'" in connection.sql


async def test_gold_claim_evidence_sample_requires_matching_production_documents() -> None:
    connection = _ScalarConnection(True)

    assert await _gold_sample_is_authoritative(
        connection,
        sample_kind=GoldSampleKind.CLAIM_EVIDENCE,
        identities=(
            UUID("019b1700-0000-7000-8000-000000000005"),
            UUID("019b1700-0000-7000-8000-000000000006"),
        ),
        source_id=UUID("019b1700-0000-7000-8000-000000000001"),
    )
    assert "evidence.claim_id=claim.id" in connection.sql
    assert "claim_version.execution_domain='PRODUCTION'" in connection.sql
    assert "evidence_version.execution_domain='PRODUCTION'" in connection.sql
    assert "claim_document.source_id=:source" in connection.sql
    assert "evidence_document.source_id=:source" in connection.sql


async def test_gold_search_question_fails_closed_without_an_authoritative_entity() -> None:
    connection = _ScalarConnection(True)

    assert not await _gold_sample_is_authoritative(
        connection,
        sample_kind=GoldSampleKind.SEARCH_QUESTION,
        identities=(UUID("019b1700-0000-7000-8000-000000000007"),),
        source_id=UUID("019b1700-0000-7000-8000-000000000001"),
    )
    assert connection.sql == ""


def test_gold_domain_is_derived_from_authoritative_source_content_domains() -> None:
    assert _source_supports_gold_domain(
        ("DIGITAL_TRANSFORMATION_CASE", "RESEARCH_PAPER"), "DIGITAL"
    )
    assert not _source_supports_gold_domain(("SAFETY_REGULATION",), "DIGITAL")
    assert _source_supports_gold_domain(
        ("ACCIDENT_INVESTIGATION", "OFFICIAL_NOTICE"), "SAFETY"
    )
    assert not _source_supports_gold_domain(("UNKNOWN",), "SAFETY")


async def test_gold_annotation_evidence_requires_accepted_production_source_facts() -> None:
    source_id = UUID("019b1700-0000-7000-8000-000000000001")
    evidence_ids = (
        UUID("019b1700-0000-7000-8000-000000000008"),
        UUID("019b1700-0000-7000-8000-000000000009"),
    )
    connection = _ScalarConnection(2)

    assert await _gold_annotation_evidence_is_authoritative(
        connection,
        evidence_ids=evidence_ids,
        source_id=source_id,
        sample_kind=GoldSampleKind.DOCUMENT,
        sample_ref="urn:srbg:document:019b1700-0000-7000-8000-000000000002",
    )
    assert "claim_row.verification_status='ACCEPTED'" in connection.sql
    assert "claim_document.source_id=:source" in connection.sql
    assert "evidence_document.source_id=:source" in connection.sql
    assert "claim_version.execution_domain='PRODUCTION'" in connection.sql
    assert "evidence_version.execution_domain='PRODUCTION'" in connection.sql
    assert "admission_fixture=false" in connection.sql
    assert connection.parameters["expected_count"] == 2

    connection.result = 1
    assert not await _gold_annotation_evidence_is_authoritative(
        connection,
        evidence_ids=evidence_ids,
        source_id=source_id,
        sample_kind=GoldSampleKind.DOCUMENT,
        sample_ref="urn:srbg:document:019b1700-0000-7000-8000-000000000002",
    )


async def test_claim_evidence_annotation_is_exactly_bound_to_task_reference() -> None:
    connection = _ScalarConnection(1)
    claim_id = "019b1700-0000-7000-8000-000000000010"
    evidence_id = UUID("019b1700-0000-7000-8000-000000000011")
    sample_ref = f"urn:srbg:claim-evidence:{claim_id}:{evidence_id}"

    assert await _gold_annotation_evidence_is_authoritative(
        connection,
        evidence_ids=(evidence_id,),
        source_id=UUID("019b1700-0000-7000-8000-000000000001"),
        sample_kind=GoldSampleKind.CLAIM_EVIDENCE,
        sample_ref=sample_ref,
    )
    assert connection.parameters["sample_claim"] == UUID(claim_id)
    assert connection.parameters["sample_evidence"] == evidence_id

    assert not await _gold_annotation_evidence_is_authoritative(
        connection,
        evidence_ids=(UUID("019b1700-0000-7000-8000-000000000012"),),
        source_id=UUID("019b1700-0000-7000-8000-000000000001"),
        sample_kind=GoldSampleKind.CLAIM_EVIDENCE,
        sample_ref=sample_ref,
    )


def test_gold_release_sources_must_equal_the_exact_twenty_source_window_roster() -> None:
    source_codes = tuple(f"SRC-{number:03d}" for number in range(1, 21))

    assert _gold_release_sources_match_window(source_codes, source_codes)
    assert not _gold_release_sources_match_window(source_codes[:-1], source_codes)
    assert not _gold_release_sources_match_window((), ("SRC-001",))
    assert not _gold_release_sources_match_window(
        ("SRC-001", "OUT-999"), ("SRC-001", "SRC-002")
    )


def test_round17_start_requires_server_attestation_and_exact_authoritative_snapshot() -> None:
    source_codes = tuple(f"SRC-{number:03d}" for number in range(1, 21))
    window = {
        "roster_version": "r17-sources-v0.1",
        "metric_definition_version": "phase2-round17-metrics-v1.0.0",
        "gold_definition_version": "phase2-round17-gold-v1.0.0",
        "baseline_commit": "a" * 40,
        "config_version": "r17-config-v0.1",
        "database_revision": "0017b_round17_pilot",
    }

    missing = _round17_snapshot_blockers(
        window,
        observed_source_codes=source_codes,
        current_database_revision="0017b_round17_pilot",
        baseline_commit_attestation=None,
        config_version_attestation=None,
        authoritative_source_codes=None,
    )
    assert missing == {
        "ROUND17_BASELINE_COMMIT_ATTESTATION_MISSING",
        "ROUND17_CONFIG_VERSION_ATTESTATION_MISSING",
        "ROUND17_ROSTER_ATTESTATION_MISSING",
    }

    assert not _round17_snapshot_blockers(
        window,
        observed_source_codes=source_codes,
        current_database_revision="0017b_round17_pilot",
        baseline_commit_attestation="a" * 40,
        config_version_attestation="r17-config-v0.1",
        authoritative_source_codes=source_codes,
    )


def test_round17_schedule_attestation_is_exact_and_fails_closed() -> None:
    source_codes = tuple(f"SRC-{number:03d}" for number in range(1, 21))
    observed = {
        code: (21_600, 28_800)
        for code in source_codes
    }

    assert _round17_schedule_attestation_blockers(observed, None) == {
        "ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISSING"
    }
    assert not _round17_schedule_attestation_blockers(observed, observed)

    wrong_slo = dict(observed)
    wrong_slo[source_codes[0]] = (21_600, 64_800)
    assert _round17_schedule_attestation_blockers(wrong_slo, observed) == {
        "ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISMATCH"
    }

    wrong_roster = dict(observed)
    wrong_roster.pop(source_codes[-1])
    wrong_roster["OUT-999"] = (21_600, 28_800)
    assert _round17_schedule_attestation_blockers(wrong_roster, observed) == {
        "ROUND17_SOURCE_SCHEDULE_ATTESTATION_ROSTER_MISMATCH"
    }

    wrong_authority = dict(observed)
    wrong_authority[source_codes[1]] = (21_601, 28_800)
    assert _round17_schedule_attestation_blockers(
        observed,
        observed,
        authoritative_source_schedules=wrong_authority,
    ) == {"ROUND17_SOURCE_SCHEDULE_AUTHORITY_MISMATCH"}


def test_round17_schedule_interval_and_slo_keep_distinct_authorities() -> None:
    policy = {
        "fetch": {"minimum_interval_seconds": 900},
        "slo": {"applicability": "APPLICABLE", "target_minutes": 480},
    }

    assert _round17_schedule_values_from_authority(360, policy) == (21_600, 28_800)
    assert _round17_schedule_values_from_authority(
        360, policy | {"fetch": {"minimum_interval_seconds": 1}}
    ) == (21_600, 28_800)
    assert _round17_schedule_values_from_authority(
        360,
        policy | {"slo": {"applicability": "NOT_APPLICABLE", "target_minutes": None}}
    ) == (21_600, None)
    assert _round17_schedule_values_from_authority(True, policy) == (None, None)


def test_round17_schedule_writes_fail_closed_for_roster_sources() -> None:
    source_codes = tuple(f"SRC-{number:03d}" for number in range(1, 21))
    attested = {code: (21_600, 28_800) for code in source_codes}

    assert _round17_schedule_write_blockers(
        source_code=source_codes[0],
        observed_schedule=(21_600, 28_800),
        authoritative_source_schedule=(21_600, 28_800),
        attested_schedules=attested,
        authoritative_source_codes=source_codes,
    ) == set()
    assert _round17_schedule_write_blockers(
        source_code=source_codes[0],
        observed_schedule=(21_600, 28_800),
        authoritative_source_schedule=(21_600, 28_800),
        attested_schedules=None,
        authoritative_source_codes=source_codes,
    ) == {"ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISSING"}
    assert _round17_schedule_write_blockers(
        source_code=source_codes[0],
        observed_schedule=(21_600, 28_800),
        authoritative_source_schedule=(21_600, 64_800),
        attested_schedules=attested,
        authoritative_source_codes=source_codes,
    ) == {"ROUND17_SOURCE_SCHEDULE_AUTHORITY_MISMATCH"}


def test_round17_prepare_t0_and_schedule_write_all_bind_policy_and_attestation() -> None:
    source = Path("apps/api/src/srbg_api/operations/service.py").read_text(
        encoding="utf-8"
    )
    prepare = source.split("async def prepare_pilot_window", 1)[1].split(
        "async def list_pilot_windows", 1
    )[0]
    start = source.split("async def start_pilot_window", 1)[1].split(
        "async def list_gold_tasks", 1
    )[0]
    schedule_write = source.split("async def update_schedule", 1)[1].split(
        "async def source_health", 1
    )[0]

    for boundary, policy_alias in (
        (prepare, "policy.document AS policy_document"),
        (start, "p.document AS policy_document"),
    ):
        assert policy_alias in boundary
        assert "_round17_schedule_attestation_blockers" in boundary
        assert "authoritative_source_schedules=" in boundary
    assert "_round17_schedule_write_blockers" in schedule_write
    assert "p.document AS policy_document" in schedule_write


def test_round17_mutations_require_the_single_server_attested_leo_actor() -> None:
    trusted = UUID("019b1700-0000-7000-8000-000000000098")
    same_name_other_actor = UUID("019b1700-0000-7000-8000-000000000097")

    assert _round17_leo_actor_is_attested(trusted, trusted)
    assert not _round17_leo_actor_is_attested(same_name_other_actor, trusted)
    assert not _round17_leo_actor_is_attested(trusted, None)


def test_round17_start_reads_eventization_pin_for_every_source_and_fails_closed() -> None:
    service = Path("apps/api/src/srbg_api/operations/service.py").read_text(
        encoding="utf-8"
    )
    start = service.split("async def start_pilot_window", 1)[1].split(
        "async def list_gold_tasks", 1
    )[0]

    assert "round17_eventization_readiness" in start
    assert "eventization_pipeline_ready" in start
    assert "SOURCE_EVENTIZATION_PIPELINE_NOT_READY" in Path(
        "apps/api/src/srbg_api/operations/round17.py"
    ).read_text(encoding="utf-8")

    source_codes = tuple(f"SRC-{number:03d}" for number in range(1, 21))
    window = {
        "roster_version": "r17-sources-v0.1",
        "metric_definition_version": "phase2-round17-metrics-v1.0.0",
        "gold_definition_version": "phase2-round17-gold-v1.0.0",
        "baseline_commit": "a" * 40,
        "config_version": "r17-config-v0.1",
        "database_revision": "0017b_round17_pilot",
    }
    mismatched = dict(window)
    mismatched["roster_version"] = "r17-sources-v9.9"
    mismatched["metric_definition_version"] = "phase2-round17-metrics-v9.9.9"
    mismatched["gold_definition_version"] = "phase2-round17-gold-v9.9.9"
    blockers = _round17_snapshot_blockers(
        mismatched,
        observed_source_codes=(*source_codes[:-1], "ALT-999"),
        current_database_revision="different-head",
        baseline_commit_attestation="b" * 40,
        config_version_attestation="different-config",
        authoritative_source_codes=source_codes,
    )
    assert blockers == {
        "ROUND17_BASELINE_COMMIT_ATTESTATION_MISMATCH",
        "ROUND17_CONFIG_VERSION_ATTESTATION_MISMATCH",
        "ROUND17_DATABASE_REVISION_MISMATCH",
        "ROUND17_GOLD_DEFINITION_VERSION_MISMATCH",
        "ROUND17_METRIC_DEFINITION_VERSION_MISMATCH",
        "ROUND17_ROSTER_SOURCE_CODES_MISMATCH",
        "ROUND17_ROSTER_VERSION_MISMATCH",
    }


def test_eventization_readiness_requires_a_hash_bound_external_signature() -> None:
    actor_id = UUID("019b1700-0000-7000-8000-000000000098")
    source_id = UUID("019b1700-0000-7000-8000-000000000001")
    policy_id = UUID("019b1700-0000-7000-8000-000000000002")
    config_id = UUID("019b1700-0000-7000-8000-000000000003")
    trial_id = UUID("019b1700-0000-7000-8000-000000000004")
    decision_id = UUID("019b1700-0000-7000-8000-000000000005")
    readiness: dict[str, object] = {
        "source_id": source_id,
        "policy_version_id": policy_id,
        "connector_config_version_id": config_id,
        "trial_run_id": trial_id,
        "production_decision_id": decision_id,
        "business_parser_profile_version": "parser-v1",
        "business_parser_profile_sha256": "1" * 64,
        "claim_evidence_profile_version": "claim-v1",
        "claim_evidence_profile_sha256": "2" * 64,
        "event_identity_profile_version": "event-v1",
        "event_identity_profile_sha256": "3" * 64,
        "publication_projection_profile_version": "projection-v1",
        "publication_projection_profile_sha256": "4" * 64,
        "verification_manifest_ref": (
            "urn:srbg:round17-eventization-manifest:"
            "019b1700-0000-7000-8000-000000000006"
        ),
        "verified_by": actor_id,
    }
    manifest = {
        "schema_version": "round17-eventization-manifest-v1",
        "source_code": "SRC-001",
        "source_id": str(source_id),
        "policy_version_id": str(policy_id),
        "connector_config_version_id": str(config_id),
        "trial_run_id": str(trial_id),
        "production_decision_id": str(decision_id),
        "business_parser_profile": {"version": "parser-v1", "sha256": "1" * 64},
        "claim_evidence_profile": {"version": "claim-v1", "sha256": "2" * 64},
        "event_identity_profile": {"version": "event-v1", "sha256": "3" * 64},
        "publication_projection_profile": {
            "version": "projection-v1",
            "sha256": "4" * 64,
        },
        "verification_manifest_ref": readiness["verification_manifest_ref"],
        "outcome": "PASSED",
    }
    import json

    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    readiness["verification_manifest"] = manifest
    readiness["verification_manifest_sha256"] = sha256(canonical).hexdigest()
    readiness["verification_signature"] = b64encode(private_key.sign(canonical)).decode()
    readiness["signer_public_key_sha256"] = sha256(public_key).hexdigest()

    assert _eventization_manifest_is_trusted(
        readiness,
        source_code="SRC-001",
        leo_actor_id=actor_id,
        trusted_public_key_base64=b64encode(public_key).decode(),
        trusted_public_key_sha256=sha256(public_key).hexdigest(),
    )

    tampered = dict(readiness)
    tampered["business_parser_profile_sha256"] = "f" * 64
    assert not _eventization_manifest_is_trusted(
        tampered,
        source_code="SRC-001",
        leo_actor_id=actor_id,
        trusted_public_key_base64=b64encode(public_key).decode(),
        trusted_public_key_sha256=sha256(public_key).hexdigest(),
    )
    assert not _eventization_manifest_is_trusted(
        readiness,
        source_code="SRC-001",
        leo_actor_id=actor_id,
        trusted_public_key_base64=None,
        trusted_public_key_sha256=None,
    )

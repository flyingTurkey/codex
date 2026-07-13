import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from srbg_api.source_registry.admission import (
    REQUIRED_ONBOARDING_CHECKS,
    AdmissionRejected,
    build_onboarding_record,
    build_policy_record,
)
from srbg_contracts import SourceOnboardingSubmission, SourcePolicySubmission

SOURCE_ID = UUID("019b0000-0000-7000-8000-000000000001")
ACTOR_ID = UUID("019b0000-0000-7000-8000-000000009001")
HASH = "a" * 64
REQUIRED_CODES = (
    "OWNER_VERIFIED",
    "ROBOTS_REVIEWED",
    "TERMS_REVIEWED",
    "COPYRIGHT_POLICY_SET",
    "RATE_LIMIT_SET",
    "DOMAIN_ALLOWLIST_SET",
    "THIRTY_FIXTURES_VALIDATED",
    "CONTRACT_TEST_PASS",
    "STRUCTURE_BASELINE_SET",
    "SECURITY_TEST_PASS",
    "OWNER_ASSIGNED",
)


def _assert_json_schema(value: object, schema: dict[str, Any], root: dict[str, Any]) -> None:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        assert reference.startswith("#/$defs/")
        definition = root["$defs"][reference.removeprefix("#/$defs/")]
        _assert_json_schema(value, definition, root)
        return

    if "enum" in schema:
        assert value in schema["enum"]
    if "const" in schema:
        assert value == schema["const"]

    schema_type = schema.get("type")
    if schema_type == "object":
        assert isinstance(value, dict)
        assert set(schema.get("required", ())).issubset(value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties)
        for key, child in properties.items():
            if key in value:
                _assert_json_schema(value[key], child, root)
    elif schema_type == "array":
        assert isinstance(value, list)
        assert len(value) >= schema.get("minItems", 0)
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            assert len(serialized) == len(set(serialized))
        for item in value:
            _assert_json_schema(item, schema["items"], root)
    elif schema_type == "string":
        assert isinstance(value, str)
        assert len(value) >= schema.get("minLength", 0)
        if pattern := schema.get("pattern"):
            assert re.search(pattern, value)
        if schema.get("format") == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif schema_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value >= schema.get("minimum", value)
        assert value <= schema.get("maximum", value)
    elif schema_type == "boolean":
        assert isinstance(value, bool)


def _policy(now: datetime) -> SourcePolicySubmission:
    return SourcePolicySubmission.model_validate(
        {
            "policy_version": "1.0.0",
            "status": "VALID",
            "robots_review": {
                "result": "ALLOWED",
                "evidence_url": "https://example.test/robots.txt",
                "evidence_sha256": HASH,
                "checked_at": now.isoformat(),
            },
            "terms_review": {
                "result": "NOT_PRESENT",
                "evidence_url": "https://example.test/terms-review",
                "evidence_sha256": HASH,
                "checked_at": now.isoformat(),
            },
            "copyright": {
                "storage_policy": "RAW_EVIDENCE_ALLOWED",
                "display_policy": "METADATA_EXCERPT_LINK",
                "fulltext_allowed": False,
                "image_allowed": False,
                "excerpt_max_chars": 300,
                "attribution_template": "来源: {source_name}",
            },
            "access": {
                "allowed_domains": ["example.test"],
                "requires_auth": False,
                "rate_limit_per_minute": 10,
                "user_agent": "SRBGSourceAdapter/1.0",
            },
            "review": {
                "valid_until": (now + timedelta(days=90)).isoformat(),
                "approval_id": "approval-001",
            },
        }
    )


def test_policy_record_injects_authoritative_source_and_reviewer_fields() -> None:
    now = datetime.now(UTC)

    record = build_policy_record(SOURCE_ID, _policy(now), ACTOR_ID, now)

    assert record["source_id"] == str(SOURCE_ID)
    assert record["review"]["reviewed_by"] == str(ACTOR_ID)
    assert record["review"]["reviewed_at"] == now.isoformat()
    assert record["robots_review"]["evidence_sha256"] != HASH
    assert set(record) == {
        "source_id",
        "policy_version",
        "status",
        "robots_review",
        "terms_review",
        "copyright",
        "access",
        "review",
    }


def test_onboarding_record_rejects_missing_checks_and_server_computes_fixture_evidence() -> None:
    now = datetime.now(UTC)
    incomplete = SourceOnboardingSubmission.model_validate(
        {
            "checks": [
                {"code": code, "evidence_ref": f"evidence:{code}", "evidence_sha256": HASH}
                for code in REQUIRED_CODES[:-1]
            ]
            + [
                {
                    "code": REQUIRED_CODES[-2],
                    "evidence_ref": "duplicate",
                    "evidence_sha256": HASH,
                }
            ],
            "valid_until": (now + timedelta(days=90)).isoformat(),
        }
    )

    with pytest.raises(AdmissionRejected, match="required onboarding checks"):
        build_onboarding_record(
            SOURCE_ID,
            "1.0.0",
            incomplete,
            ACTOR_ID,
            now,
            fixture_hashes=[f"{index:064x}" for index in range(30)],
        )

    complete = SourceOnboardingSubmission.model_validate(
        {
            "checks": [
                {
                    "code": code,
                    "evidence_ref": f"evidence:{code}",
                    "evidence_sha256": HASH,
                }
                for code in REQUIRED_CODES
            ],
            "valid_until": incomplete.valid_until.isoformat(),
        }
    )
    record = build_onboarding_record(
        SOURCE_ID,
        "1.0.0",
        complete,
        ACTOR_ID,
        now,
        fixture_hashes=[f"{index:064x}" for index in range(30)],
    )

    assert record["sample_count"] == 30
    assert record["fixture_set_sha256"] != HASH
    assert all(check["passed"] is True for check in record["checks"])
    assert record["decision"] == "APPROVED"


def test_onboarding_requires_thirty_distinct_content_hashes() -> None:
    now = datetime.now(UTC)
    submission = SourceOnboardingSubmission.model_validate(
        {
            "checks": [
                {"code": code, "evidence_ref": f"evidence:{code}", "evidence_sha256": HASH}
                for code in REQUIRED_CODES
            ],
            "valid_until": (now + timedelta(days=90)).isoformat(),
        }
    )

    with pytest.raises(AdmissionRejected, match="30 distinct"):
        build_onboarding_record(
            SOURCE_ID,
            "1.0.0",
            submission,
            ACTOR_ID,
            now,
            fixture_hashes=[HASH] * 30,
        )


def test_preview_submissions_do_not_require_human_calculated_evidence_hashes() -> None:
    now = datetime.now(UTC)
    policy_payload = _policy(now).model_dump(mode="json")
    policy_payload["robots_review"].pop("evidence_sha256")
    policy_payload["terms_review"].pop("evidence_sha256")
    submission = SourcePolicySubmission.model_validate(policy_payload)

    record = build_policy_record(SOURCE_ID, submission, ACTOR_ID, now)

    assert len(record["robots_review"]["evidence_sha256"]) == 64
    assert len(record["terms_review"]["evidence_sha256"]) == 64


def test_persisted_records_pass_the_canonical_json_schemas() -> None:
    now = datetime.now(UTC)
    policy_record = build_policy_record(SOURCE_ID, _policy(now), ACTOR_ID, now)
    onboarding_submission = SourceOnboardingSubmission.model_validate(
        {
            "checks": [
                {"code": code, "evidence_ref": f"evidence:{code}"} for code in REQUIRED_CODES
            ],
            "valid_until": (now + timedelta(days=90)).isoformat(),
        }
    )
    onboarding_record = build_onboarding_record(
        SOURCE_ID,
        "1.0.0",
        onboarding_submission,
        ACTOR_ID,
        now,
        fixture_hashes=[f"{index:064x}" for index in range(30)],
    )
    schemas = Path("docs/codex-kit/assets/schemas")
    policy_schema = json.loads((schemas / "source-policy.schema.json").read_text(encoding="utf-8"))
    onboarding_schema = json.loads(
        (schemas / "source-onboarding-record.schema.json").read_text(encoding="utf-8")
    )

    _assert_json_schema(policy_record, policy_schema, policy_schema)
    _assert_json_schema(onboarding_record, onboarding_schema, onboarding_schema)

    checklist = json.loads(
        Path("docs/codex-kit/assets/validation/source_onboarding_checklist.json").read_text(
            encoding="utf-8"
        )
    )
    canonical_codes = {item["code"] for item in checklist["required_checks"]}
    assert REQUIRED_ONBOARDING_CHECKS == canonical_codes

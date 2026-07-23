import inspect

from srbg_api.intelligence_v2.safety_exceptions import (
    classify_safety_signals,
    safe_safety_evidence_locators,
)
from srbg_api.intelligence_v2.technical_exceptions import (
    PostgresOwnerTechnicalExceptionService,
)


def test_server_classifies_owner_decidable_content_signals() -> None:
    prompt_injection = classify_safety_signals(["PROMPT_INJECTION"])
    suspicious = classify_safety_signals(["SUSPICIOUS_PATTERN"])

    assert prompt_injection.overrideability.value == "OWNER_DECIDABLE"
    assert prompt_injection.reason.value == "PROMPT_INJECTION_DETECTED"
    assert suspicious.overrideability.value == "OWNER_DECIDABLE"
    assert suspicious.reason.value == "SUSPICIOUS_MODEL_SIGNAL"


def test_server_fail_closes_hard_and_unrecognized_security_signals() -> None:
    expected = {
        "PRIVATE_NETWORK_TARGET": "PRIVATE_NETWORK_TARGET",
        "LOOPBACK_TARGET": "LOOPBACK_TARGET",
        "CLOUD_METADATA_TARGET": "CLOUD_METADATA_TARGET",
        "MALICIOUS_PAYLOAD": "MALICIOUS_PAYLOAD",
        "ACCESS_CONTROL_BYPASS": "ACCESS_CONTROL_BYPASS",
        "MANDATORY_MALWARE_SCAN_FAILED": "MANDATORY_MALWARE_SCAN_FAILED",
        "MALWARE_SCAN_FAILED": "MANDATORY_MALWARE_SCAN_FAILED",
        "MALWARE_SCAN_INCONCLUSIVE": "MANDATORY_MALWARE_SCAN_FAILED",
        "SAFE_BYTES_UNAVAILABLE": "SAFE_BYTES_UNAVAILABLE",
        "MODEL_CLAIMS_RISK_RESOLVED": "UNRECOGNIZED_SECURITY_SIGNAL",
    }
    for signal, reason in expected.items():
        classification = classify_safety_signals([signal])
        assert classification.overrideability.value == "HARD_BLOCK"
        assert classification.reason.value == reason


def test_primary_type_is_not_a_platform_security_signal() -> None:
    assert classify_safety_signals([]) is None


def test_safety_evidence_is_restricted_to_server_issued_locators() -> None:
    assert safe_safety_evidence_locators(
        ["019f7900-0000-7000-8000-000000000001", "invented", "other"],
        frozenset({"019f7900-0000-7000-8000-000000000001", "other-safe"}),
    ) == ["019f7900-0000-7000-8000-000000000001"]


def test_safety_commands_serialize_and_resume_durable_pending_actions() -> None:
    guard = inspect.getsource(PostgresOwnerTechnicalExceptionService._command_safety)
    command = inspect.getsource(PostgresOwnerTechnicalExceptionService._command_safety_locked)

    assert "pg_advisory_xact_lock" in guard
    pending = command.split(
        'metadata.get("last_reevaluation_status") == "PENDING"', 1
    )[1].split("IDEMPOTENT_REPLAY", 1)[0]
    assert "_apply_safety_action" in pending

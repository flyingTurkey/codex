"""Server-owned classification for content-processing safety signals."""

from __future__ import annotations

from dataclasses import dataclass

from srbg_contracts import SafetyOverrideability, SafetyRiskReason


@dataclass(frozen=True, slots=True)
class SafetySignalClassification:
    reason: SafetyRiskReason
    overrideability: SafetyOverrideability


_OWNER_DECIDABLE = {
    "PROMPT_INJECTION": SafetyRiskReason.PROMPT_INJECTION_DETECTED,
    "PROMPT_INJECTION_DETECTED": SafetyRiskReason.PROMPT_INJECTION_DETECTED,
    "SUSPICIOUS_PATTERN": SafetyRiskReason.SUSPICIOUS_MODEL_SIGNAL,
    "SUSPICIOUS_MODEL_SIGNAL": SafetyRiskReason.SUSPICIOUS_MODEL_SIGNAL,
}
_HARD_BLOCK = {
    reason.value: reason
    for reason in (
        SafetyRiskReason.PRIVATE_NETWORK_TARGET,
        SafetyRiskReason.LOOPBACK_TARGET,
        SafetyRiskReason.CLOUD_METADATA_TARGET,
        SafetyRiskReason.MALICIOUS_PAYLOAD,
        SafetyRiskReason.ACCESS_CONTROL_BYPASS,
        SafetyRiskReason.MANDATORY_MALWARE_SCAN_FAILED,
        SafetyRiskReason.SAFE_BYTES_UNAVAILABLE,
    )
}
_HARD_BLOCK.update(
    {
        "MALWARE_SCAN_FAILED": SafetyRiskReason.MANDATORY_MALWARE_SCAN_FAILED,
        "MALWARE_SCAN_INCONCLUSIVE": SafetyRiskReason.MANDATORY_MALWARE_SCAN_FAILED,
    }
)


def classify_safety_signals(
    signals: list[str] | tuple[str, ...],
) -> SafetySignalClassification | None:
    """Map untrusted signal labels onto closed server authority."""

    normalized = tuple(sorted({signal.strip().upper() for signal in signals if signal.strip()}))
    if not normalized:
        return None
    for signal in normalized:
        reason = _HARD_BLOCK.get(signal)
        if reason is not None:
            return SafetySignalClassification(
                reason=reason,
                overrideability=SafetyOverrideability.HARD_BLOCK,
            )
    unknown = next(
        (signal for signal in normalized if signal not in _OWNER_DECIDABLE),
        None,
    )
    if unknown is not None:
        return SafetySignalClassification(
            reason=SafetyRiskReason.UNRECOGNIZED_SECURITY_SIGNAL,
            overrideability=SafetyOverrideability.HARD_BLOCK,
        )
    return SafetySignalClassification(
        reason=_OWNER_DECIDABLE[normalized[0]],
        overrideability=SafetyOverrideability.OWNER_DECIDABLE,
    )


def safe_safety_evidence_locators(
    candidate_locators: list[str] | tuple[str, ...],
    allowed_locators: frozenset[str],
) -> list[str]:
    """Retain only server-issued locators for an untrusted safety signal."""

    return sorted(set(candidate_locators).intersection(allowed_locators))

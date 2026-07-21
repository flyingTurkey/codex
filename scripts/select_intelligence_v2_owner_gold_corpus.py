"""Deterministically select a fresh Owner Gold corpus from a preregistered frame."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from srbg_api.identifiers import uuid7

_CORPUS_VERSION = "owner-gold-2026-07-20.5"
_FRAME_SCHEMA_VERSION = "intelligence-v2-owner-gold-candidate-frame-1.0.0"
_SELECTION_ALGORITHM = "canonical-url-sha256-per-preregistered-slot-v1"
_NEGATIVE_FAMILIES = (
    "PURE_MEDICAL_HEALTH",
    "PROCESS_ONLY_NOTICE",
    "NON_CIVIL_DIGITALIZATION",
    "NON_CIVIL_SAFETY",
    "NON_CONSTRUCTION_EQUIPMENT",
)
_VERSION_KEYS = (
    "rule_version",
    "model_id",
    "model_profile_version",
    "prompt_version",
    "model_schema_version",
    "owner_gold_schema_version",
)


def _positive_specification(
    primary_type: str,
    objects: tuple[str, ...],
    *,
    central_fact_kind: str,
    specialty: tuple[str, ...] = (),
    equipment: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "sampling_stratum": "POSITIVE",
        "sampling_primary_type": primary_type,
        "boundary_family": None,
        "negative_family": None,
        "central_fact_kind": central_fact_kind,
        "engineering_objects": list(objects),
        "specialty_facets": list(specialty),
        "equipment_domains": list(equipment),
    }


def required_selection_slots() -> dict[str, dict[str, object]]:
    """Return the preregistered 40 cells; two or more candidates are required per cell."""

    slots: dict[str, dict[str, object]] = {
        "P-DIGITAL-01": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("HIGHWAY",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
        ),
        "P-DIGITAL-02": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("RAILWAY",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
        ),
        "P-DIGITAL-03": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("RAILWAY",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
        ),
        "P-DIGITAL-04": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("BUILDING",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
        ),
        "P-DIGITAL-05": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("WATER_CONSERVANCY",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
        ),
        "P-DIGITAL-06": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("HIGHWAY",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
            equipment=("CONSTRUCTION_MACHINERY",),
        ),
        "P-DIGITAL-07": _positive_specification(
            "DIGITAL_TRANSFORMATION",
            ("BUILDING",),
            central_fact_kind="ENGINEERING_DIGITAL_APPLICATION",
            equipment=("CONSTRUCTION_MACHINERY",),
        ),
        "P-SAFETY-01": _positive_specification(
            "SAFETY_INTELLIGENCE",
            ("HIGHWAY", "TUNNEL"),
            central_fact_kind="SUBSTANTIVE_SAFETY_RULE",
            specialty=("TUNNEL_GAS_MONITORING",),
        ),
        "P-SAFETY-02": _positive_specification(
            "SAFETY_INTELLIGENCE", ("MINING",), central_fact_kind="SUBSTANTIVE_SAFETY_RULE"
        ),
        "P-SAFETY-03": _positive_specification(
            "SAFETY_INTELLIGENCE", ("MUNICIPAL",), central_fact_kind="SUBSTANTIVE_SAFETY_RULE"
        ),
        "P-SAFETY-04": _positive_specification(
            "SAFETY_INTELLIGENCE", ("ENERGY",), central_fact_kind="SUBSTANTIVE_SAFETY_RULE"
        ),
        "P-SAFETY-05": _positive_specification(
            "SAFETY_INTELLIGENCE",
            ("MUNICIPAL", "ENERGY"),
            central_fact_kind="SUBSTANTIVE_SAFETY_RULE",
        ),
        "P-SAFETY-06": _positive_specification(
            "SAFETY_INTELLIGENCE", ("RAILWAY",), central_fact_kind="SUBSTANTIVE_SAFETY_RULE"
        ),
        "P-SAFETY-07": _positive_specification(
            "SAFETY_INTELLIGENCE", ("HIGHWAY",), central_fact_kind="SUBSTANTIVE_SAFETY_RULE"
        ),
        "P-INDUSTRY-01": _positive_specification(
            "INDUSTRY_UPDATE", ("HIGHWAY", "BRIDGE"), central_fact_kind="PROJECT_OPENED"
        ),
        "P-INDUSTRY-02": _positive_specification(
            "INDUSTRY_UPDATE", ("RAILWAY", "TUNNEL"), central_fact_kind="TUNNEL_BREAKTHROUGH"
        ),
        "P-INDUSTRY-03": _positive_specification(
            "INDUSTRY_UPDATE", ("PORT_WATERWAY",), central_fact_kind="PROJECT_COMMISSIONED"
        ),
        "P-INDUSTRY-04": _positive_specification(
            "INDUSTRY_UPDATE", ("AIRPORT",), central_fact_kind="PROJECT_COMPLETED"
        ),
        "P-INDUSTRY-05": _positive_specification(
            "INDUSTRY_UPDATE", ("WATER_CONSERVANCY",), central_fact_kind="PROJECT_COMMISSIONED"
        ),
        "P-INDUSTRY-06": _positive_specification(
            "INDUSTRY_UPDATE",
            ("ENERGY",),
            central_fact_kind="MAJOR_CONSTRUCTION_MILESTONE",
        ),
    }
    central_by_negative_family = {
        "PURE_MEDICAL_HEALTH": "PURE_MEDICAL_HEALTH",
        "PROCESS_ONLY_NOTICE": "PROCESS_ONLY",
        "NON_CIVIL_DIGITALIZATION": "NON_CIVIL_DIGITALIZATION",
        "NON_CIVIL_SAFETY": "NON_CIVIL_SAFETY",
        "NON_CONSTRUCTION_EQUIPMENT": "NON_CONSTRUCTION_EQUIPMENT",
    }
    for family in _NEGATIVE_FAMILIES:
        for ordinal in (1, 2, 3, 4):
            slots[f"N-{family}-{ordinal}"] = {
                "sampling_stratum": "NEGATIVE",
                "sampling_primary_type": None,
                "boundary_family": None,
                "negative_family": family,
                "central_fact_kind": central_by_negative_family[family],
                "engineering_objects": [],
                "specialty_facets": [],
                "equipment_domains": [],
            }
    return slots


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("OWNER_GOLD_CANDIDATE_URL_INVALID")
    hostname = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    path = parsed.path or "/"
    return urlunsplit(("https", hostname + port, path, parsed.query, ""))


def build_candidate_frame(
    sources: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    preregistered_at: datetime,
    versions: Mapping[str, object],
) -> dict[str, object]:
    """Expand a private URL pool into the immutable preregistered candidate frame."""

    if preregistered_at.tzinfo is None:
        raise ValueError("OWNER_GOLD_PREREGISTRATION_TIMESTAMP_INVALID")
    slots = required_selection_slots()
    if set(sources) != set(slots):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_SLOT_MISMATCH")
    if any(not str(versions.get(key) or "").strip() for key in _VERSION_KEYS):
        raise ValueError("OWNER_GOLD_SOURCE_POOL_VERSION_INVALID")
    candidates: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    for slot, specification in slots.items():
        alternatives = sources[slot]
        if len(alternatives) < 2:
            raise ValueError(f"OWNER_GOLD_SOURCE_POOL_TOO_SMALL:{slot}")
        for ordinal, source in enumerate(alternatives, 1):
            canonical_url = canonicalize_url(str(source.get("canonical_url") or ""))
            if canonical_url in seen_urls:
                raise ValueError("OWNER_GOLD_SOURCE_POOL_URL_DUPLICATE")
            title = str(source.get("discovery_title") or "").strip()
            if not title:
                raise ValueError("OWNER_GOLD_SOURCE_POOL_TITLE_INVALID")
            seen_urls.add(canonical_url)
            candidates.append(
                {
                    "candidate_id": f"{slot}-C{ordinal:02d}",
                    "selection_slot": slot,
                    "canonical_url": canonical_url,
                    "discovery_title": title,
                    **specification,
                }
            )
    return {
        "schema_version": _FRAME_SCHEMA_VERSION,
        "corpus_version": _CORPUS_VERSION,
        "selection_algorithm": _SELECTION_ALGORITHM,
        "preregistered_at": preregistered_at.isoformat(),
        "candidate_count": len(candidates),
        **{key: str(versions[key]) for key in _VERSION_KEYS},
        "candidates": candidates,
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_candidate_against_slot(
    candidate: Mapping[str, object], slot: str, specification: Mapping[str, object]
) -> None:
    if not str(candidate.get("candidate_id") or "").strip():
        raise ValueError("OWNER_GOLD_CANDIDATE_ID_INVALID")
    if candidate.get("selection_slot") != slot:
        raise ValueError("OWNER_GOLD_CANDIDATE_SLOT_INVALID")
    for key, expected in specification.items():
        if candidate.get(key) != expected:
            raise ValueError(f"OWNER_GOLD_CANDIDATE_PREREGISTRATION_MISMATCH:{slot}:{key}")
    if not str(candidate.get("discovery_title") or "").strip():
        raise ValueError("OWNER_GOLD_CANDIDATE_TITLE_INVALID")
    canonicalize_url(str(candidate.get("canonical_url") or ""))


def select_candidate_frame(
    frame: Mapping[str, object],
    *,
    prior_corpus_manifest: Mapping[str, object] | None = None,
    prior_corpus_manifests: Sequence[Mapping[str, object]] | None = None,
    selected_at: datetime,
) -> dict[str, object]:
    """Validate preregistration and SHA-order each slot without consulting labels."""

    if selected_at.tzinfo is None:
        raise ValueError("OWNER_GOLD_SELECTION_TIMESTAMP_INVALID")
    if (
        frame.get("schema_version") != _FRAME_SCHEMA_VERSION
        or frame.get("corpus_version") != _CORPUS_VERSION
        or frame.get("selection_algorithm") != _SELECTION_ALGORITHM
    ):
        raise ValueError("OWNER_GOLD_CANDIDATE_FRAME_VERSION_INVALID")
    if any(not str(frame.get(key) or "").strip() for key in _VERSION_KEYS):
        raise ValueError("OWNER_GOLD_CANDIDATE_FRAME_MODEL_VERSION_INVALID")
    raw_candidates = frame.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) < 80:
        raise ValueError("OWNER_GOLD_CANDIDATE_FRAME_TOO_SMALL")
    if not all(isinstance(value, dict) for value in raw_candidates):
        raise ValueError("OWNER_GOLD_CANDIDATE_INVALID")
    candidates = cast(list[dict[str, object]], raw_candidates)
    candidate_ids = [str(value.get("candidate_id") or "") for value in candidates]
    canonical_urls = [
        canonicalize_url(str(value.get("canonical_url") or "")) for value in candidates
    ]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("OWNER_GOLD_CANDIDATE_ID_DUPLICATE")
    if len(set(canonical_urls)) != len(canonical_urls):
        raise ValueError("OWNER_GOLD_CANDIDATE_URL_DUPLICATE")

    if prior_corpus_manifest is not None and prior_corpus_manifests is not None:
        raise ValueError("OWNER_GOLD_PRIOR_CORPUS_MANIFEST_ARGUMENT_CONFLICT")
    manifests = (
        list(prior_corpus_manifests)
        if prior_corpus_manifests is not None
        else [prior_corpus_manifest or {"cases": []}]
    )
    prior_cases: list[object] = []
    for manifest in manifests:
        raw_prior_cases = manifest.get("cases")
        if not isinstance(raw_prior_cases, list):
            raise ValueError("OWNER_GOLD_PRIOR_CORPUS_MANIFEST_INVALID")
        prior_cases.extend(raw_prior_cases)
    prior_case_ids = {
        str(value.get("case_id") or "") for value in prior_cases if isinstance(value, dict)
    }
    prior_urls = {
        canonicalize_url(str(value.get("source_url") or ""))
        for value in prior_cases
        if isinstance(value, dict) and value.get("source_url")
    }
    prior_content_hashes = {
        str(value.get("content_sha256") or "")
        for value in prior_cases
        if isinstance(value, dict) and value.get("content_sha256")
    }
    if prior_case_ids & set(candidate_ids):
        raise ValueError("OWNER_GOLD_PRIOR_CASE_ID_REUSED")
    if prior_urls & set(canonical_urls):
        raise ValueError("OWNER_GOLD_PRIOR_CANONICAL_URL_REUSED")
    if any(
        str(candidate.get("known_content_sha256") or "") in prior_content_hashes
        for candidate in candidates
        if candidate.get("known_content_sha256")
    ):
        raise ValueError("OWNER_GOLD_PRIOR_CONTENT_HASH_REUSED")

    slots = required_selection_slots()
    by_slot: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for candidate, canonical_url in zip(candidates, canonical_urls, strict=True):
        slot = str(candidate.get("selection_slot") or "")
        specification = slots.get(slot)
        if specification is None:
            raise ValueError("OWNER_GOLD_CANDIDATE_SLOT_UNKNOWN")
        _validate_candidate_against_slot(candidate, slot, specification)
        by_slot[slot].append({**candidate, "canonical_url": canonical_url})
    if set(by_slot) != set(slots) or any(len(by_slot[slot]) < 2 for slot in slots):
        raise ValueError("OWNER_GOLD_CANDIDATE_FRAME_TOO_SMALL")

    cases: list[dict[str, object]] = []
    for slot, specification in slots.items():
        chain = sorted(
            by_slot[slot],
            key=lambda value: sha256(str(value["canonical_url"]).encode("utf-8")).hexdigest(),
        )
        cases.append(
            {
                "case_id": str(uuid7()),
                "selection_slot": slot,
                **specification,
                "candidate_chain": chain,
            }
        )
    distribution = Counter(value["sampling_stratum"] for value in cases)
    if distribution != {"POSITIVE": 20, "NEGATIVE": 20}:
        raise AssertionError("preregistered slot distribution drifted")
    selected: dict[str, object] = {
        "schema_version": "intelligence-v2-owner-gold-selection-plan-1.0.0",
        "corpus_version": _CORPUS_VERSION,
        "selection_algorithm": _SELECTION_ALGORITHM,
        "selected_at": selected_at.isoformat(),
        "candidate_count": len(candidates),
        "candidate_frame_sha256": sha256(_canonical_json(frame)).hexdigest(),
        "prior_corpus_manifest_sha256": sha256(_canonical_json(manifests)).hexdigest(),
        "excluded_case_ids": sorted(prior_case_ids),
        "excluded_canonical_urls": sorted(prior_urls),
        "excluded_content_sha256": sorted(prior_content_hashes),
        "cases": cases,
    }
    selected.update({key: frame[key] for key in _VERSION_KEYS})
    return selected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-frame", type=Path, required=True)
    parser.add_argument(
        "--prior-corpus-manifest", type=Path, action="append", required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("OWNER_GOLD_SELECTION_PLAN_ALREADY_EXISTS")
    selected = select_candidate_frame(
        json.loads(args.candidate_frame.read_text(encoding="utf-8")),
        prior_corpus_manifests=[
            json.loads(path.read_text(encoding="utf-8"))
            for path in args.prior_corpus_manifest
        ],
        selected_at=datetime.now(UTC),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OWNER_GOLD_SELECTION_PLAN_CREATED:40:{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest

from scripts.freeze_intelligence_v2_owner_gold_corpus import (
    _normalize_html,
    validate_frozen_content,
)
from scripts.retarget_intelligence_v2_owner_gold_source_pool import apply_source_pool_amendment
from scripts.select_intelligence_v2_owner_gold_corpus import (
    build_candidate_frame,
    required_selection_slots,
    select_candidate_frame,
)


def _candidate_frame() -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for slot, specification in required_selection_slots().items():
        for alternative in ("a", "b"):
            candidates.append(
                {
                    "candidate_id": f"{slot}-{alternative}",
                    "selection_slot": slot,
                    "canonical_url": f"https://official.example.gov.cn/{slot}/{alternative}.html",
                    "discovery_title": f"公开一手材料 {slot} {alternative}",
                    **specification,
                }
            )
    return {
        "schema_version": "intelligence-v2-owner-gold-candidate-frame-1.0.0",
        "corpus_version": "owner-gold-2026-07-20.5",
        "selection_algorithm": "canonical-url-sha256-per-preregistered-slot-v1",
        "preregistered_at": "2026-07-20T10:00:00+00:00",
        "rule_version": "intelligence-v2-qualification-1.0.0",
        "model_id": "deepseek-v4-flash",
        "model_profile_version": "ai-provider-profile-deepseek-v1",
        "prompt_version": "ai01-classify-v1",
        "model_schema_version": "classify-output-v1",
        "owner_gold_schema_version": "intelligence-v2-owner-gold-2.0.0",
        "candidates": candidates,
    }


def test_candidate_frame_has_two_preregistered_candidates_for_each_of_40_slots() -> None:
    slots = required_selection_slots()

    assert len(slots) == 40
    assert sum(value["sampling_stratum"] == "POSITIVE" for value in slots.values()) == 20
    assert sum(value["sampling_stratum"] == "BOUNDARY" for value in slots.values()) == 0
    assert sum(value["sampling_stratum"] == "NEGATIVE" for value in slots.values()) == 20
    assert {
        family: sum(value.get("negative_family") == family for value in slots.values())
        for family in {
            "PURE_MEDICAL_HEALTH",
            "PROCESS_ONLY_NOTICE",
            "NON_CIVIL_DIGITALIZATION",
            "NON_CIVIL_SAFETY",
            "NON_CONSTRUCTION_EQUIPMENT",
        }
    } == {
        "PURE_MEDICAL_HEALTH": 4,
        "PROCESS_ONLY_NOTICE": 4,
        "NON_CIVIL_DIGITALIZATION": 4,
        "NON_CIVIL_SAFETY": 4,
        "NON_CONSTRUCTION_EQUIPMENT": 4,
    }
    assert (
        sum(
            value.get("sampling_primary_type") == "DIGITAL_TRANSFORMATION"
            for value in slots.values()
        )
        == 7
    )
    assert (
        sum(value.get("sampling_primary_type") == "SAFETY_INTELLIGENCE" for value in slots.values())
        == 7
    )
    assert (
        sum(value.get("sampling_primary_type") == "INDUSTRY_UPDATE" for value in slots.values())
        == 6
    )
    assert {obj for value in slots.values() for obj in value["engineering_objects"]} == {
        "HIGHWAY",
        "RAILWAY",
        "BRIDGE",
        "TUNNEL",
        "BUILDING",
        "MINING",
        "MUNICIPAL",
        "WATER_CONSERVANCY",
        "PORT_WATERWAY",
        "AIRPORT",
        "ENERGY",
    }
    assert (
        sum("CONSTRUCTION_MACHINERY" in value["equipment_domains"] for value in slots.values()) >= 2
    )


def test_candidate_frame_builder_injects_preregistered_slot_metadata() -> None:
    sources = {
        slot: [
            {
                "canonical_url": f"https://official.example.gov.cn/{slot}/{alternative}.html",
                "discovery_title": f"public source {slot} {alternative}",
            }
            for alternative in ("a", "b")
        ]
        for slot in required_selection_slots()
    }

    frame = build_candidate_frame(
        sources,
        preregistered_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
        versions={
            "rule_version": "intelligence-v2-qualification-1.0.0",
            "model_id": "deepseek-v4-flash",
            "model_profile_version": "ai-provider-profile-deepseek-v1",
            "prompt_version": "ai01-classify-v1",
            "model_schema_version": "classify-output-v1",
            "owner_gold_schema_version": "intelligence-v2-owner-gold-2.0.0",
        },
    )

    assert frame["candidate_count"] == 80
    candidate = frame["candidates"][0]
    assert candidate["selection_slot"] in required_selection_slots()
    assert candidate["candidate_id"].startswith(candidate["selection_slot"] + "-")
    assert candidate["sampling_stratum"] in {"POSITIVE", "NEGATIVE"}


def test_candidate_frame_builder_rejects_missing_or_duplicate_sources() -> None:
    sources = {
        slot: [
            {
                "canonical_url": f"https://official.example.gov.cn/{slot}/{alternative}.html",
                "discovery_title": f"public source {slot} {alternative}",
            }
            for alternative in ("a", "b")
        ]
        for slot in required_selection_slots()
    }
    sources["P-DIGITAL-01"] = sources["P-DIGITAL-01"][:1]

    with pytest.raises(ValueError, match="OWNER_GOLD_SOURCE_POOL_TOO_SMALL"):
        build_candidate_frame(
            sources,
            preregistered_at=datetime(2026, 7, 20, 10, tzinfo=UTC),
            versions={
                "rule_version": "rule",
                "model_id": "model",
                "model_profile_version": "profile",
                "prompt_version": "prompt",
                "model_schema_version": "model-schema",
                "owner_gold_schema_version": "owner-schema",
            },
        )


def test_source_pool_amendment_retargets_version_without_mutating_the_base() -> None:
    base = {
        "schema_version": "intelligence-v2-owner-gold-source-pool-1.0.0",
        "corpus_version": "owner-gold-2026-07-20.2",
        "preregistered_at": "2026-07-20T10:00:00+00:00",
        "slots": {
            "P-DIGITAL-02": [
                {"canonical_url": "https://old.example.gov.cn/a", "discovery_title": "old a"},
                {"canonical_url": "https://old.example.gov.cn/b", "discovery_title": "old b"},
            ]
        },
    }
    amendment = {
        "schema_version": "intelligence-v2-owner-gold-source-pool-amendment-1.0.0",
        "corpus_version": "owner-gold-2026-07-20.3",
        "preregistered_at": "2026-07-20T13:00:00+00:00",
        "replacements": {
            "P-DIGITAL-02": [
                {"canonical_url": "https://new.example.gov.cn/a", "discovery_title": "new a"},
                {"canonical_url": "https://new.example.gov.cn/b", "discovery_title": "new b"},
            ]
        },
    }

    resolved = apply_source_pool_amendment(base, amendment)

    assert resolved["corpus_version"] == "owner-gold-2026-07-20.3"
    assert resolved["slots"]["P-DIGITAL-02"] == amendment["replacements"]["P-DIGITAL-02"]
    assert base["slots"]["P-DIGITAL-02"][0]["discovery_title"] == "old a"


def test_candidate_selection_is_sha_ordered_and_emits_new_uuidv7_case_ids() -> None:
    selected = select_candidate_frame(
        _candidate_frame(),
        prior_corpus_manifest={"cases": []},
        selected_at=datetime(2026, 7, 20, 11, tzinfo=UTC),
    )

    assert selected["corpus_version"] == "owner-gold-2026-07-20.5"
    assert selected["candidate_count"] == 80
    assert len(selected["cases"]) == 40
    for case in selected["cases"]:
        assert UUID(case["case_id"]).version == 7
        urls = [candidate["canonical_url"] for candidate in case["candidate_chain"]]
        assert urls == sorted(
            urls,
            key=lambda value: sha256(value.encode()).hexdigest(),
        )


def test_candidate_selection_rejects_any_prior_url_case_or_content_identity() -> None:
    frame = _candidate_frame()
    first = frame["candidates"][0]
    prior = {
        "cases": [
            {
                "case_id": "019f7e60-6728-7413-a053-c69617d6d5b3",
                "source_url": first["canonical_url"],
                "content_sha256": "a" * 64,
            }
        ]
    }

    with pytest.raises(ValueError, match="OWNER_GOLD_PRIOR_CANONICAL_URL_REUSED"):
        select_candidate_frame(
            frame,
            prior_corpus_manifest=prior,
            selected_at=datetime(2026, 7, 20, 11, tzinfo=UTC),
        )


def test_candidate_selection_rejects_identity_from_any_prior_manifest() -> None:
    frame = _candidate_frame()
    first = frame["candidates"][0]
    priors = [
        {"cases": []},
        {
            "cases": [
                {
                    "case_id": "019f7e60-6728-7413-a053-c69617d6d5b3",
                    "source_url": first["canonical_url"],
                    "content_sha256": "b" * 64,
                }
            ]
        },
    ]

    with pytest.raises(ValueError, match="OWNER_GOLD_PRIOR_CANONICAL_URL_REUSED"):
        select_candidate_frame(
            frame,
            prior_corpus_manifests=priors,
            selected_at=datetime(2026, 7, 20, 11, tzinfo=UTC),
        )


def test_candidate_frame_rejects_fewer_than_80_candidates() -> None:
    frame = _candidate_frame()
    frame["candidates"] = frame["candidates"][:-1]

    with pytest.raises(ValueError, match="OWNER_GOLD_CANDIDATE_FRAME_TOO_SMALL"):
        select_candidate_frame(
            frame,
            prior_corpus_manifest={"cases": []},
            selected_at=datetime(2026, 7, 20, 11, tzinfo=UTC),
        )


def test_notice_and_medical_rules_are_based_on_central_fact_not_title_alone() -> None:
    substantive_notice = {
        "sampling_stratum": "POSITIVE",
        "sampling_primary_type": "SAFETY_INTELLIGENCE",
        "central_fact_kind": "SUBSTANTIVE_SAFETY_RULE",
        "negative_family": None,
    }
    validate_frozen_content(
        substantive_notice,
        title="关于加强隧道施工安全的通知",
        normalized_content="本通知规定隧道施工必须部署有害气体连续监测和超限报警装置。",
    )

    process_only = {
        "sampling_stratum": "NEGATIVE",
        "sampling_primary_type": None,
        "central_fact_kind": "PROCESS_ONLY",
        "negative_family": "PROCESS_ONLY_NOTICE",
    }
    validate_frozen_content(
        process_only,
        title="关于报送申报名单的通知",
        normalized_content="请各单位在规定时间报送申报材料和联系人名单。",
    )
    with pytest.raises(ValueError, match="PROCESS_ONLY_NOTICE_CONTAINS_ENGINEERING_FACT"):
        validate_frozen_content(
            process_only,
            title="关于项目进展的通知",
            normalized_content="高速公路隧道已正式通车并投入运营。",
        )


def test_positive_design_objects_facets_and_equipment_must_be_visible_in_body() -> None:
    bridge_candidate = {
        "sampling_stratum": "POSITIVE",
        "sampling_primary_type": "DIGITAL_TRANSFORMATION",
        "central_fact_kind": "ENGINEERING_DIGITAL_APPLICATION",
        "negative_family": None,
        "engineering_objects": ["BRIDGE"],
        "specialty_facets": [],
        "equipment_domains": [],
    }
    with pytest.raises(ValueError, match="POSITIVE_ENGINEERING_OBJECT_NOT_EVIDENCED:BRIDGE"):
        validate_frozen_content(
            bridge_candidate,
            title="铁路站房智能建造",
            normalized_content="项目使用BIM平台和施工机器人推进铁路站房数字化建设。",
        )

    gas_candidate = {
        **bridge_candidate,
        "sampling_primary_type": "SAFETY_INTELLIGENCE",
        "engineering_objects": ["HIGHWAY", "TUNNEL"],
        "specialty_facets": ["TUNNEL_GAS_MONITORING"],
    }
    with pytest.raises(ValueError, match="POSITIVE_TUNNEL_GAS_NOT_EVIDENCED"):
        validate_frozen_content(
            gas_candidate,
            title="公路隧道施工安全规则",
            normalized_content="本规则要求公路隧道施工落实安全检查和应急处置。",
        )

    machinery_candidate = {
        **bridge_candidate,
        "engineering_objects": ["HIGHWAY"],
        "equipment_domains": ["CONSTRUCTION_MACHINERY"],
    }
    with pytest.raises(ValueError, match="POSITIVE_CONSTRUCTION_MACHINERY_NOT_EVIDENCED"):
        validate_frozen_content(
            machinery_candidate,
            title="公路数字化管理平台",
            normalized_content="项目通过数字平台管理公路施工进度。",
        )

    pure_medical = {
        "sampling_stratum": "NEGATIVE",
        "sampling_primary_type": None,
        "central_fact_kind": "PURE_MEDICAL_HEALTH",
        "negative_family": "PURE_MEDICAL_HEALTH",
    }
    validate_frozen_content(
        pure_medical,
        title="合理用药健康科普",
        normalized_content="本文介绍药品使用、临床诊疗和居民健康管理知识。",
    )
    with pytest.raises(ValueError, match="PURE_MEDICAL_CASE_CONTAINS_ENGINEERING_FACT"):
        validate_frozen_content(
            pure_medical,
            title="医院改扩建工程开工",
            normalized_content="医院新院区建筑施工项目已经开工, 施工现场实施安全管理。",
        )


def test_html_normalization_keeps_visible_body_blocks_and_filters_navigation() -> None:
    raw = """
    <html><head><title>隧道施工监测实施</title></head><body>
      <nav><a href='/a'>首页</a><a href='/b'>通知公告</a></nav>
      <article>
        <h1>隧道施工监测实施</h1>
        <p>项目在铁路隧道施工区域部署有害气体连续监测设备。</p>
        <p>监测系统已接入施工安全平台并形成超限报警处置闭环。</p>
      </article>
      <div><a href='/x'>推荐阅读一</a> <a href='/y'>推荐阅读二</a></div>
      <footer>版权所有 联系我们 网站地图</footer>
    </body></html>
    """.encode()

    title, normalized, locators = _normalize_html(raw)

    assert title == "隧道施工监测实施"
    assert "铁路隧道施工区域" in normalized
    assert "监测系统已接入" in normalized
    assert "首页" not in normalized
    assert "推荐阅读" not in normalized
    assert "版权所有" not in normalized
    assert len(locators) == len(normalized.split("\n\n"))
    assert all(locator.startswith("html:") and ":sha256:" in locator for locator in locators)

from __future__ import annotations

# ruff: noqa: RUF001
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.autonomous_policy import (
    AdjudicationInput,
    AutomatedAdjudicationService,
    QualificationPolicyBundle,
    build_classification_system_prompt,
)
from srbg_contracts import QualificationDecisionTrace


def _bundle(**overrides: object) -> QualificationPolicyBundle:
    values: dict[str, object] = {
        "policy_version": "qualification-policy-2.0.0",
        "global_rule_version": "global-rules-2.0.0",
        "source_stream_policy_version": "stream-policy-7",
        "ai_provider": "protocol-equivalent-test",
        "ai_model": "semantic-classifier-v2",
        "prompt_version": "autonomous-classify-2.0.0",
        "schema_version": "autonomous-classify-output-2.0.0",
        "code_version": "issue-41-test",
        "source_allow_terms": ("施工", "监测"),
        "source_exclude_terms": ("招聘",),
    }
    values.update(overrides)
    return QualificationPolicyBundle.create(**values)  # type: ignore[arg-type]


def test_policy_bundle_digest_is_stable_and_binds_every_component() -> None:
    first = _bundle()
    same = _bundle()
    changed = _bundle(prompt_version="autonomous-classify-2.0.1")

    assert first.identity == same.identity
    assert len(first.identity.bundle_sha256) == 64
    assert changed.identity.bundle_sha256 != first.identity.bundle_sha256


class RecordingModelEdge:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls = 0
        self.semantic_rechecks: list[bool] = []

    def classify(
        self, *, system_prompt: str, document_text: str, semantic_recheck: bool
    ) -> dict[str, object]:
        self.calls += 1
        self.semantic_rechecks.append(semantic_recheck)
        return self.responses.pop(0)


class TimeoutModelEdge:
    def classify(
        self, *, system_prompt: str, document_text: str, semantic_recheck: bool
    ) -> dict[str, object]:
        raise TimeoutError


class RecordingDecisionSink:
    def __init__(self) -> None:
        self.traces: list[QualificationDecisionTrace] = []

    def append(self, trace: QualificationDecisionTrace) -> None:
        self.traces.append(trace)


def _input(text: str) -> AdjudicationInput:
    return AdjudicationInput(
        document_version_id=UUID("019b1d00-0000-7000-8000-000000000042"),
        raw_object_id=UUID("019b1d00-0000-7000-8000-000000000043"),
        normalized_input_sha256="b" * 64,
        document_text=text,
        allowed_evidence_locators=frozenset({"html:p:8"}),
    )


def _candidate(**overrides: object) -> dict[str, object]:
    return {
        "direct_relevance": "RELEVANT",
        "core_new_fact": "铁路隧道施工启动安全整治",
        "primary_type": "SAFETY_INTELLIGENCE",
        "engineering_objects": ["RAILWAY", "TUNNEL"],
        "specialty_facets": [],
        "equipment_domains": [],
        "content_form": "AUTHORITY_NOTICE",
        "evidence_locators": ["html:p:8"],
        "ambiguity_indicators": [],
        "security_signals": [],
        "confidence": 0.01,
    } | overrides


def test_locked_negative_filters_before_any_model_call() -> None:
    model = RecordingModelEdge([])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("旅游消费促销活动启动，与工程建设无关。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert [reason.value for reason in trace.reason_codes] == ["RULE_LOCKED_NEGATIVE"]
    assert trace.model_candidate is None
    assert trace.policy == _bundle().identity
    assert model.calls == 0


def test_tourism_context_does_not_filter_a_central_bridge_construction_fact() -> None:
    model = RecordingModelEdge(
        [
            _candidate(
                core_new_fact="旅游区跨河桥梁施工正式启动",
                primary_type="INDUSTRY_UPDATE",
                engineering_objects=["BRIDGE"],
            )
        ]
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("旅游区跨河桥梁施工正式启动。"))

    assert trace.disposition.value == "AUTO_ACCEPTED"
    assert model.calls == 1


def test_health_context_does_not_filter_a_central_building_construction_fact() -> None:
    model = RecordingModelEdge(
        [
            _candidate(
                core_new_fact="中医药医院房屋建筑工程开工",
                primary_type="INDUSTRY_UPDATE",
                engineering_objects=["BUILDING"],
            )
        ]
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("中医药医院房屋建筑工程正式开工建设。"))

    assert trace.disposition.value == "AUTO_ACCEPTED"
    assert model.calls == 1


@pytest.mark.parametrize(
    "text",
    [
        "Tourism resort hotel promotion launched.",
        "Stock market index and fund quotation update.",
        "Consumer electronics manufacturing line expansion.",
        "工程机械企业 ERP 系统升级并优化内部经营管理。",
        "港口企业发布年度经营业绩，营收与利润增长。",
    ],
)
def test_locked_negative_categories_filter_before_model(text: str) -> None:
    model = RecordingModelEdge([])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input(text))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert trace.reason_codes[0].value == "RULE_LOCKED_NEGATIVE"
    assert model.calls == 0


def test_missing_engineering_object_activity_cooccurrence_filters_before_model() -> None:
    model = RecordingModelEdge([])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("某企业发布季度经营信息。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert [reason.value for reason in trace.reason_codes] == ["RULE_NO_ENGINEERING_COOCCURRENCE"]
    assert model.calls == 0


def test_semantic_model_can_supply_an_unlexicalized_engineering_object() -> None:
    model = RecordingModelEdge(
        [
            _candidate(
                core_new_fact="Underground transit depot construction started",
                primary_type="INDUSTRY_UPDATE",
                engineering_objects=["RAILWAY"],
            )
        ]
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(
        _input("Underground transit depot construction started this month.")
    )

    assert trace.disposition.value == "AUTO_ACCEPTED"
    assert "AI_SUPPORTED_ENGINEERING_OBJECT_ACTIVITY_COOCCURRENCE" in trace.rule_signals


def test_transient_model_failure_becomes_technical_retry_without_owner_task() -> None:
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=TimeoutModelEdge(),
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert trace.disposition.value == "TECHNICAL_RETRY"
    assert [reason.value for reason in trace.reason_codes] == ["TECHNICAL_RETRYABLE"]
    assert trace.model_candidate is None
    assert trace.semantic_recheck_count == 0


def test_confidence_is_diagnostic_and_cannot_replace_server_gates() -> None:
    model = RecordingModelEdge([_candidate()])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    accepted = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert accepted.disposition.value == "AUTO_ACCEPTED"
    assert accepted.model_candidate is not None
    assert accepted.model_candidate.confidence == 0.01
    assert model.calls == 1


def test_model_cannot_accept_without_an_engineering_object_axis() -> None:
    missing_axis = _candidate(engineering_objects=[])
    model = RecordingModelEdge([missing_axis, missing_axis])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("工程施工活动形成新的行业事实。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert "RULE_NO_ENGINEERING_COOCCURRENCE" in {
        reason.value for reason in trace.reason_codes
    }
    assert trace.semantic_recheck_count == 1


def test_every_adjudication_can_be_appended_through_the_persistence_seam() -> None:
    sink = RecordingDecisionSink()
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=RecordingModelEdge([_candidate()]),
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
        decision_sink=sink,
    )

    returned = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert sink.traces == [returned]


def test_rule_ai_conflict_gets_one_recheck_then_auto_filters() -> None:
    conflicting = _candidate(
        primary_type="DIGITAL_TRANSFORMATION",
        confidence=1.0,
    )
    model = RecordingModelEdge([conflicting, conflicting])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert trace.semantic_recheck_count == 1
    assert [reason.value for reason in trace.reason_codes] == [
        "AI_RULE_CONFLICT",
        "AI_AMBIGUITY_UNRESOLVED",
    ]
    assert model.semantic_rechecks == [False, True]


def test_security_signal_enters_safety_hold_without_semantic_override() -> None:
    model = RecordingModelEdge([_candidate(security_signals=["PROMPT_INJECTION"])])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert trace.disposition.value == "SAFETY_HOLD"
    assert [reason.value for reason in trace.reason_codes] == ["SAFETY_SIGNAL"]
    assert trace.semantic_recheck_count == 0
    assert model.calls == 1


def test_prompt_contains_frozen_domain_and_untrusted_document_boundaries() -> None:
    prompt = build_classification_system_prompt(_bundle())

    for required in (
        "DirectRelevance",
        "EngineeringObject",
        "TUNNEL_GAS_MONITORING",
        "CONSTRUCTION_MACHINERY",
        "PrimaryType",
        "SAFETY_INTELLIGENCE > DIGITAL_TRANSFORMATION > INDUSTRY_UPDATE",
        "SourceStream",
        "CENTRAL_FACT_TEST",
        "LOCKED_NEGATIVE_CATEGORIES",
        "traditional medicine and general health",
        "tourism and consumer promotion",
        "financial market quotations",
        "generic AI",
        "port business performance",
        "ERP, production-line, or generic industrial-internet",
        "same evidence-supported fact",
        "SUBJECT_ACTION_OBJECT_CHECK",
        "one to three evidence locators",
        "company profile, customer list, example, or future aspiration",
        "port logistics or commercial throughput",
        "COUNTERFACTUAL_BACKGROUND_REMOVAL",
        "cross-industry standard or policy",
        "qualification, award, meeting, survey, or publicity",
        "central novelty is the engineering application",
        "证据锚点",
        "不可信输入",
        "不得改变规则",
        "不得输出发布状态",
    ):
        assert required in prompt


@pytest.mark.parametrize(
    ("object_code", "object_text"),
    [
        ("HIGHWAY", "公路"),
        ("RAILWAY", "铁路"),
        ("BRIDGE", "桥梁"),
        ("TUNNEL", "隧道"),
        ("BUILDING", "房屋建筑"),
        ("MINING", "矿山"),
        ("MUNICIPAL", "市政"),
        ("WATER_CONSERVANCY", "水利"),
        ("PORT_WATERWAY", "港航"),
        ("AIRPORT", "机场"),
        ("ENERGY", "能源工程"),
    ],
)
def test_all_engineering_objects_can_be_rule_supported(object_code: str, object_text: str) -> None:
    model = RecordingModelEdge(
        [
            _candidate(
                core_new_fact=f"{object_text}建设取得新进展",
                primary_type="INDUSTRY_UPDATE",
                engineering_objects=[object_code],
            )
        ]
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input(f"{object_text}建设取得新进展。"))

    assert trace.disposition.value == "AUTO_ACCEPTED"


def test_safety_primary_type_wins_when_document_also_mentions_digitalization() -> None:
    model = RecordingModelEdge([_candidate(primary_type="SAFETY_INTELLIGENCE")])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("铁路隧道施工数字化安全整治。"))

    assert trace.disposition.value == "AUTO_ACCEPTED"
    assert model.calls == 1
    assert trace.model_candidate is not None
    assert trace.model_candidate.primary_type.value == "SAFETY_INTELLIGENCE"


def test_background_safety_term_does_not_override_central_digital_fact() -> None:
    candidate = _candidate(
        core_new_fact="Bridge digital monitoring platform launched",
        primary_type="DIGITAL_TRANSFORMATION",
        engineering_objects=["BRIDGE"],
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=RecordingModelEdge([candidate]),
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(
        _input("Bridge digital monitoring platform launched. Background accident records followed.")
    )

    assert trace.disposition.value == "AUTO_ACCEPTED"


def test_mining_gas_stays_mining_and_cannot_use_tunnel_gas_specialty() -> None:
    invalid = _candidate(
        core_new_fact="矿井瓦斯安全监测升级",
        engineering_objects=["MINING"],
        specialty_facets=["TUNNEL_GAS_MONITORING"],
    )
    model = RecordingModelEdge([invalid, invalid])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("矿井建设采用瓦斯安全监测措施。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert "RULE_AXIS_INVARIANT_FAILED" in {reason.value for reason in trace.reason_codes}


def test_construction_machinery_requires_direct_in_scope_lifecycle_use() -> None:
    candidate = _candidate(
        core_new_fact="挖掘机直接用于公路施工",
        primary_type="INDUSTRY_UPDATE",
        engineering_objects=["HIGHWAY"],
        equipment_domains=["CONSTRUCTION_MACHINERY"],
    )
    model = RecordingModelEdge([candidate])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("挖掘机直接用于公路施工。"))

    assert trace.disposition.value == "AUTO_ACCEPTED"


def test_construction_machinery_rejects_cross_sentence_keyword_cooccurrence() -> None:
    candidate = _candidate(
        core_new_fact="Excavator sales rose",
        primary_type="INDUSTRY_UPDATE",
        engineering_objects=["HIGHWAY"],
        equipment_domains=["CONSTRUCTION_MACHINERY"],
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=RecordingModelEdge([candidate, candidate]),
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(
        _input("Highway construction continued. Excavator consumer sales rose.")
    )

    assert trace.disposition.value == "AUTO_FILTERED"
    assert "RULE_AXIS_INVARIANT_FAILED" in {reason.value for reason in trace.reason_codes}


def test_schema_invalid_model_output_gets_one_correction_then_filters() -> None:
    malformed = _candidate(publication_status="PUBLISHED")
    model = RecordingModelEdge([malformed, malformed])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert [reason.value for reason in trace.reason_codes] == ["AI_SCHEMA_INVALID"]
    assert trace.model_candidate is None
    assert trace.semantic_recheck_count == 1
    assert model.semantic_rechecks == [False, True]


def test_invalid_schema_after_semantic_recheck_fails_closed() -> None:
    semantically_invalid = _candidate(primary_type="DIGITAL_TRANSFORMATION")
    model = RecordingModelEdge([semantically_invalid, {"unexpected": True}])
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=model,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(_input("铁路隧道施工启动安全整治。"))

    assert trace.disposition.value == "AUTO_FILTERED"
    assert [reason.value for reason in trace.reason_codes] == ["AI_SCHEMA_INVALID"]
    assert trace.semantic_recheck_count == 1

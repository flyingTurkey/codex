# ruff: noqa: RUF001
"""Generated structural replay corpus; never evidence of human-reviewed quality."""

from dataclasses import dataclass
from typing import Literal

from srbg_contracts import EngineeringObject, PrimaryIntelligenceType

CORPUS_VERSION = "civil-intelligence-structural-replay-v2.0.0"


@dataclass(frozen=True)
class StructuralReplayCase:
    case_id: str
    text: str
    bucket: Literal["POSITIVE", "BOUNDARY", "NEGATIVE"]
    directly_relevant: bool | None
    primary_type: PrimaryIntelligenceType | None
    engineering_object: EngineeringObject | None
    locked_negative: bool = False


_OBJECTS = tuple(EngineeringObject)
_POSITIVE_TEMPLATES: dict[PrimaryIntelligenceType, str] = {
    PrimaryIntelligenceType.DIGITAL_TRANSFORMATION: (
        "{object}工程发布数字孪生施工应用记录，原文给出项目范围、部署环节和实测结果。"
    ),
    PrimaryIntelligenceType.SAFETY_INTELLIGENCE: (
        "主管机关发布{object}工程安全通报，原文载明现场风险、处置要求和证据附件。"
    ),
    PrimaryIntelligenceType.INDUSTRY_UPDATE: (
        "权威来源公布{object}工程建设运营的新进展，包含明确项目、时间和工程影响。"
    ),
}
_BOUNDARY_TEMPLATES = (
    "某地提出人工智能产业规划，只在附件中举例可能用于{object}工程。",
    "企业发布综合经营新闻，其中一段提到{object}项目但没有工程新事实。",
    "地方文旅活动借用{object}景观宣传，是否包含建设运营事实需人工复核。",
)
_NEGATIVE_TEMPLATES = (
    "中医药健康服务体系建设政策发布，与土木工程建设运营无直接关系。",
    "国民健康消费行动公布，与工程安全、建设和装备无直接关系。",
    "旅游消费促销活动启动，仅涉及景区营销。",
    "股票市场行情上涨，文章没有具体工程项目或工程技术事实。",
    "通用人工智能模型发布，未出现工程对象、施工运营或装备应用。",
)


def build_structural_replay_corpus() -> tuple[StructuralReplayCase, ...]:
    cases: list[StructuralReplayCase] = []
    for primary_type, template in _POSITIVE_TEMPLATES.items():
        for index in range(60):
            engineering_object = _OBJECTS[index % len(_OBJECTS)]
            cases.append(
                StructuralReplayCase(
                    case_id=f"P-{primary_type.value}-{index + 1:03d}",
                    text=template.format(object=engineering_object.value),
                    bucket="POSITIVE",
                    directly_relevant=True,
                    primary_type=primary_type,
                    engineering_object=engineering_object,
                )
            )
    for index in range(90):
        engineering_object = _OBJECTS[index % len(_OBJECTS)]
        cases.append(
            StructuralReplayCase(
                case_id=f"B-{index + 1:03d}",
                text=_BOUNDARY_TEMPLATES[index % len(_BOUNDARY_TEMPLATES)].format(
                    object=engineering_object.value
                ),
                bucket="BOUNDARY",
                directly_relevant=None,
                primary_type=None,
                engineering_object=engineering_object,
            )
        )
    for index in range(90):
        cases.append(
            StructuralReplayCase(
                case_id=f"N-{index + 1:03d}",
                text=_NEGATIVE_TEMPLATES[index % len(_NEGATIVE_TEMPLATES)],
                bucket="NEGATIVE",
                directly_relevant=False,
                primary_type=None,
                engineering_object=None,
                locked_negative=True,
            )
        )
    return tuple(cases)


STRUCTURAL_REPLAY_CORPUS = build_structural_replay_corpus()

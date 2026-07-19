"""Fixed, public and publication-isolated DeepSeek canary input."""

from srbg_api.ai_pipeline.preparation import (
    DocumentBlock,
    PreparedDocumentInput,
    prepare_document_input,
)

CANARY_TITLE = "土木工程情报 v2 固定运行探针"
CANARY_SOURCE = "公开固定验收文本"
CANARY_TEXT = (
    "某公开公路桥梁项目在施工阶段部署了结构监测传感器。"
    "系统用于记录应变与温度数据。本段仅用于验证分类 Schema。"
    "它不代表真实项目结论。它也不得进入发布链。"
)


def fixed_canary_input(document_version_id: str) -> PreparedDocumentInput:
    return prepare_document_input(
        document_version_id=document_version_id,
        title=CANARY_TITLE,
        source_name=CANARY_SOURCE,
        blocks=[
            DocumentBlock(
                block_id="fixed-public-canary-1",
                page_number=1,
                text=CANARY_TEXT,
                locator_value="fixed-canary:p:1",
            )
        ],
        max_characters=4_000,
    )

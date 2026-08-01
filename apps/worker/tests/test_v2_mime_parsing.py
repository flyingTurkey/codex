from uuid import UUID

from srbg_api.ai_pipeline.content_preparation import (
    PreparationDocument,
    production_policy_for_stream,
    try_deterministic_adjudication,
)
from srbg_api.ai_pipeline.preparation import DocumentBlock, prepare_document_input
from srbg_worker.ai_content_preparation import parse_html_document


def test_html_is_parsed_as_html_not_opened_as_pdf() -> None:
    parsed = parse_html_document(
        (
            "<html><body><nav>menu</nav><p>铁路隧道施工采用瓦斯监测系统。</p>"
            "<script>ignore()</script><p>系统记录报警和处置时间。</p></body></html>"
        ).encode()
    )
    assert "铁路隧道" in parsed.normalized_text
    assert "ignore" not in parsed.normalized_text
    assert len(parsed.pages[0].blocks) == 2
    assert parsed.pages[0].text_source == "NATIVE"
    assert all(block.text_source == "NATIVE" for block in parsed.pages[0].blocks)
    assert all(block.kind == "BODY" for block in parsed.pages[0].blocks)


def test_scholarly_abstract_metadata_reaches_qualification_prescan() -> None:
    title = "静动荷载下公路超大跨径管拱形钢波纹管涵洞的力学特性"
    parsed = parse_html_document(
        (
            '<html><head><meta name="citation_title" content="' + title + '">'
            '<meta name="citation_abstract" '
            'content="依托某高速公路工程 对回填施工阶段进行测试并验证模型。">'
            '<meta name="citation_publication_date" content="2026/07/30"></head>'
            '<body><p>网站版权所有。</p></body></html>'
        ).encode()
    )
    assert parsed.normalized_text.splitlines()[:3] == [
        title,
        "依托某高速公路工程 对回填施工阶段进行测试并验证模型。",
        "2026/07/30",
    ]
    blocks = [
        DocumentBlock(
            block_id=f"block-{block.block_index}",
            page_number=1,
            text=block.normalized_text,
            locator_value=f"page=1;block={block.block_index}",
        )
        for block in parsed.pages[0].blocks
    ]
    policy = production_policy_for_stream("cjht-current-issue-v1")
    document = PreparationDocument(
        run_id=UUID(int=1),
        document_version_id=UUID(int=2),
        raw_object_id=UUID(int=3),
        source_stream_policy_version="cjht-current-issue-v1",
        source_code="CJHT",
        canonical_url="https://zgglxb.chd.edu.cn/CN/frozen-document",
        title=title,
        source_name="中国公路学报",
        blocks=tuple(blocks),
        policy_bundle=policy,
    )
    prepared = prepare_document_input(
        document_version_id=str(document.document_version_id),
        title=document.title,
        source_name=document.source_name,
        blocks=blocks,
        max_characters=32_000,
    )

    assert try_deterministic_adjudication(
        document=document,
        prepared=prepared,
        policy=policy,
    ) is None

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

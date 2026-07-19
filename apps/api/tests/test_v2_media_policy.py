from srbg_api.intelligence_v2.media import bounded_signed_url_ttl, can_download, can_preview


def test_media_requires_clean_scan_and_explicit_rights() -> None:
    assert can_preview(rights_basis="EXPLICIT_LICENSE", scan_status="CLEAN")
    assert not can_preview(rights_basis=None, scan_status="CLEAN")
    assert not can_download(
        rights_basis="EXPLICIT_LICENSE", scan_status="CLEAN", redistribution_allowed=False
    )
    assert bounded_signed_url_ttl(900) == 300

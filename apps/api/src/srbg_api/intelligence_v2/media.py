"""Fail-closed reader media policy."""

ALLOWED_RIGHTS = frozenset(
    {"PUBLIC_DOMAIN", "EXPLICIT_LICENSE", "SOURCE_AUTHORIZED", "OWNER_OWNED"}
)


def can_preview(*, rights_basis: str | None, scan_status: str) -> bool:
    return rights_basis in ALLOWED_RIGHTS and scan_status == "CLEAN"


def can_download(
    *, rights_basis: str | None, scan_status: str, redistribution_allowed: bool
) -> bool:
    return (
        can_preview(rights_basis=rights_basis, scan_status=scan_status) and redistribution_allowed
    )


def bounded_signed_url_ttl(requested_seconds: int) -> int:
    if requested_seconds < 1:
        raise ValueError("signed URL TTL must be positive")
    return min(requested_seconds, 300)

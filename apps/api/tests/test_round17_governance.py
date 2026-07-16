from base64 import b64encode
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from srbg_api.auth import Principal, get_current_principal
from srbg_api.config import Settings, get_settings
from srbg_api.document_vault.service import SourceVaultMetrics
from srbg_api.main import create_app
from srbg_api.source_registry.repository import (
    ROUND17_TWO_PERSON_GOVERNANCE_SCHEME,
    SourceRow,
    SourceVaultRepository,
    _governance_separation_actor_ids,
)
from srbg_api.source_registry.service import SourceRegistryService, SourceServiceRejected
from srbg_contracts import SourceLifecycleState, SourceState, UserRole

SOURCE_ID = UUID("019b1700-0000-7000-8000-000000000001")
YINZI_ID = UUID("019b1700-0000-7000-8000-000000000002")
LEO_ID = UUID("019b1700-0000-7000-8000-000000000003")
PRIOR_APPROVER_ID = UUID("019b1700-0000-7000-8000-000000000004")


def test_round17_sole_approver_configuration_requires_uuid7() -> None:
    with pytest.raises(ValueError, match="Round 17 LEO actor must be UUIDv7"):
        Settings(round17_leo_approver_actor_id=UUID("12345678-1234-4234-8234-123456789abc"))


def _signed_local_key_material() -> tuple[str, str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return (
        b64encode(private_bytes).decode(),
        b64encode(public_bytes).decode(),
        sha256(public_bytes).hexdigest(),
    )


def test_signed_local_pilot_requires_test_environment_key_and_frozen_leo_actor() -> None:
    private_key, public_key, fingerprint = _signed_local_key_material()

    settings = Settings(
        environment="test",
        round17_authority_mode="SIGNED_LOCAL_PILOT",
        round17_leo_approver_actor_id=LEO_ID,
        round17_leo_signing_private_key_base64=private_key,
        round17_leo_signing_public_key_base64=public_key,
        round17_leo_signing_public_key_sha256=fingerprint,
    )

    assert settings.round17_authority_mode == "SIGNED_LOCAL_PILOT"
    assert settings.round17_leo_signing_private_key_base64 is not None
    assert (
        settings.round17_leo_signing_private_key_base64.get_secret_value()
        == private_key
    )


def test_signed_local_pilot_is_rejected_in_production_or_with_mismatched_key() -> None:
    private_key, public_key, fingerprint = _signed_local_key_material()

    with pytest.raises(ValueError, match="test environments only"):
        Settings(
            environment="production",
            round17_authority_mode="SIGNED_LOCAL_PILOT",
            round17_leo_approver_actor_id=LEO_ID,
            round17_leo_signing_private_key_base64=private_key,
            round17_leo_signing_public_key_base64=public_key,
            round17_leo_signing_public_key_sha256=fingerprint,
        )
    with pytest.raises(ValueError, match="key pair mismatch"):
        Settings(
            environment="test",
            round17_authority_mode="SIGNED_LOCAL_PILOT",
            round17_leo_approver_actor_id=LEO_ID,
            round17_leo_signing_private_key_base64=private_key,
            round17_leo_signing_public_key_base64=b64encode(b"x" * 32).decode(),
            round17_leo_signing_public_key_sha256=sha256(b"x" * 32).hexdigest(),
        )


def test_round17_eventization_trust_anchor_requires_exact_ed25519_fingerprint() -> None:
    public_key = b"k" * 32
    encoded = b64encode(public_key).decode()

    settings = Settings(
        _env_file=None,
        round17_eventization_trusted_public_key_base64=encoded,
        round17_eventization_trusted_public_key_sha256=sha256(public_key).hexdigest(),
    )
    assert settings.round17_eventization_trusted_public_key_base64 == encoded

    with pytest.raises(ValueError, match="configured together"):
        Settings(
            _env_file=None,
            round17_eventization_trusted_public_key_base64=encoded,
        )
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        Settings(
            _env_file=None,
            round17_eventization_trusted_public_key_base64=encoded,
            round17_eventization_trusted_public_key_sha256="f" * 64,
        )


def test_round17_schedule_attestation_configuration_is_an_exact_twenty_source_map() -> None:
    source_codes = [f"GOV-{index:03d}" for index in range(1, 21)]
    schedules = {code: (21_600, 28_800) for code in source_codes}

    settings = Settings(
        round17_roster_source_codes=source_codes,
        round17_source_schedule_attestations=schedules,
    )
    assert settings.round17_source_schedule_attestations == schedules

    with pytest.raises(ValueError, match="exactly 20 source schedules"):
        Settings(round17_source_schedule_attestations=dict(list(schedules.items())[:-1]))
    with pytest.raises(ValueError, match="must exactly match the roster"):
        Settings(
            round17_roster_source_codes=[*source_codes[:-1], "ALT-999"],
            round17_source_schedule_attestations=schedules,
        )
    with pytest.raises(ValueError, match="SLO seconds must be whole minutes"):
        Settings(
            round17_source_schedule_attestations=schedules
            | {source_codes[0]: (21_600, 28_801)}
        )
    with pytest.raises(ValueError, match="interval seconds must be whole minutes"):
        Settings(
            round17_source_schedule_attestations=schedules
            | {source_codes[0]: (21_601, 28_800)}
        )


class DummyVault:
    def __init__(self) -> None:
        self.metrics = SourceVaultMetrics()


def _source(state: SourceLifecycleState) -> SourceRow:
    return SourceRow(
        id=SOURCE_ID,
        registry_code="GOV-002",
        name="Round 17 governed source",
        base_url="https://www.gov.cn/zhengce/",
        channel="BOTH",
        source_type="government",
        authority_level="A1",
        priority="P0",
        collection_method="list_detail",
        poll_interval_minutes=360,
        owner="yinzi",
        state=SourceState.CANDIDATE,
        enabled=False,
        lifecycle_state=state,
        trial_kind=None,
        registered_by=YINZI_ID,
        governance_owner_id=YINZI_ID,
        country_codes=("CN",),
        region_codes=("CN",),
        language_tags=("zh-CN",),
        industries=("HIGHWAY",),
        content_domains=("SAFETY_REGULATION",),
        declared_roles=("OFFICIAL_PRIMARY",),
        current_policy_version_id=None,
        current_connector_config_version_id=None,
        current_trial_run_id=None,
        created_at=datetime.now(UTC),
    )


class AssignmentRepository:
    def __init__(
        self,
        state: SourceLifecycleState,
        *,
        staff_binding_matches: bool = True,
    ) -> None:
        self.source = _source(state)
        self.staff_binding_matches = staff_binding_matches
        self.staff_binding_checks: list[dict[str, object]] = []
        self.assignments: list[dict[str, object]] = []

    async def get_source(self, source_id: UUID) -> SourceRow:
        assert source_id == SOURCE_ID
        return self.source

    async def round17_source_approver_binding_matches(
        self,
        *,
        actor_id: UUID,
        display_name: str,
        authority_mode: str = "OIDC",
        oidc_issuer_sha256: str | None = None,
        oidc_subject_sha256: str | None = None,
    ) -> bool:
        self.staff_binding_checks.append(
            {
                "actor_id": actor_id,
                "display_name": display_name,
                "authority_mode": authority_mode,
                "oidc_issuer_sha256": oidc_issuer_sha256,
                "oidc_subject_sha256": oidc_subject_sha256,
            }
        )
        return self.staff_binding_matches

    async def assign_round17_governance_scheme(
        self,
        source_id: UUID,
        *,
        cohort_key: str,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> None:
        self.assignments.append(
            {
                "source_id": source_id,
                "cohort_key": cohort_key,
                "actor_id": actor_id,
                "reason": reason,
                "request_id": request_id,
                "now": now,
            }
        )


class _BindingResult:
    def scalar_one(self) -> bool:
        return True


class _BindingConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: dict[str, object] = {}

    async def execute(
        self,
        statement: object,
        params: dict[str, object],
    ) -> _BindingResult:
        self.sql = str(statement)
        self.params = params
        return _BindingResult()


class _BindingEngine:
    def __init__(self) -> None:
        self.connection = _BindingConnection()

    @asynccontextmanager
    async def connect(self):  # type: ignore[no-untyped-def]
        yield self.connection


@pytest.mark.asyncio
async def test_round17_staff_binding_query_requires_exact_non_local_source_approver() -> None:
    engine = _BindingEngine()
    repository = SourceVaultRepository(engine)  # type: ignore[arg-type]
    issuer_hash = sha256(b"https://sso.srbg.cn/realms/internal").hexdigest()
    subject_hash = sha256(b"leo-subject").hexdigest()

    assert await repository.round17_source_approver_binding_matches(
        actor_id=LEO_ID,
        display_name="LEO",
        authority_mode="OIDC",
        oidc_issuer_sha256=issuer_hash,
        oidc_subject_sha256=subject_hash,
    )

    assert "round17_staff_binding" in engine.connection.sql
    assert "responsibility='SOURCE_APPROVER'" in engine.connection.sql
    assert "local_identity=false" in engine.connection.sql
    assert engine.connection.params == {
        "actor_id": LEO_ID,
        "display_name": "LEO",
        "authority_mode": "OIDC",
        "oidc_issuer_sha256": issuer_hash,
        "oidc_subject_sha256": subject_hash,
    }


@pytest.mark.asyncio
async def test_round17_staff_binding_query_supports_only_signed_local_leo() -> None:
    engine = _BindingEngine()
    repository = SourceVaultRepository(engine)  # type: ignore[arg-type]

    assert await repository.round17_source_approver_binding_matches(
        actor_id=LEO_ID,
        display_name="LEO",
        authority_mode="SIGNED_LOCAL_PILOT",
        oidc_issuer_sha256=None,
        oidc_subject_sha256=None,
    )

    assert "authority_mode=:authority_mode" in engine.connection.sql
    assert "local_identity=true" in engine.connection.sql
    assert engine.connection.params["actor_id"] == LEO_ID


@pytest.mark.asyncio
async def test_round17_scheme_assignment_is_explicit_and_precedes_governance_decisions() -> None:
    repository = AssignmentRepository(SourceLifecycleState.CANDIDATE)
    service = SourceRegistryService(  # type: ignore[arg-type]
        repository,
        DummyVault(),
        round17_leo_approver_actor_id=LEO_ID,
    )

    await service.assign_round17_governance_scheme(
        SOURCE_ID,
        cohort_key="r17-sources-v0.1",
        reason="LEO approved the bounded Round 17 maker checker cohort",
        actor_id=LEO_ID,
        actor_display_name="LEO",
        oidc_issuer="https://sso.srbg.cn/realms/internal",
        oidc_subject="leo-subject",
        request_id="round17-governance-assignment",
    )

    assert len(repository.assignments) == 1
    assert repository.assignments[0]["cohort_key"] == "r17-sources-v0.1"
    assert repository.assignments[0]["actor_id"] == LEO_ID
    assert repository.staff_binding_checks[0]["actor_id"] == LEO_ID
    assert repository.staff_binding_checks[0]["display_name"] == "LEO"
    assert repository.staff_binding_checks[0]["oidc_issuer_sha256"] == sha256(
        b"https://sso.srbg.cn/realms/internal"
    ).hexdigest()
    assert repository.staff_binding_checks[0]["oidc_subject_sha256"] == sha256(
        b"leo-subject"
    ).hexdigest()


@pytest.mark.asyncio
async def test_signed_local_leo_can_assign_the_frozen_roster_without_oidc() -> None:
    repository = AssignmentRepository(SourceLifecycleState.CANDIDATE)
    service = SourceRegistryService(  # type: ignore[arg-type]
        repository,
        DummyVault(),
        round17_leo_approver_actor_id=LEO_ID,
        round17_authority_mode="SIGNED_LOCAL_PILOT",
    )

    await service.assign_round17_governance_scheme(
        SOURCE_ID,
        cohort_key="r17-sources-v0.1",
        reason="apply the one-signature frozen roster",
        actor_id=LEO_ID,
        actor_display_name="LEO",
        oidc_issuer=None,
        oidc_subject=None,
        request_id="round17-signed-governance-assignment",
    )

    assert repository.staff_binding_checks == [
        {
            "actor_id": LEO_ID,
            "display_name": "LEO",
            "authority_mode": "SIGNED_LOCAL_PILOT",
            "oidc_issuer_sha256": None,
            "oidc_subject_sha256": None,
        }
    ]


@pytest.mark.asyncio
async def test_round17_scheme_assignment_fails_closed_without_exact_leo_staff_binding() -> None:
    repository = AssignmentRepository(
        SourceLifecycleState.CANDIDATE,
        staff_binding_matches=False,
    )
    service = SourceRegistryService(  # type: ignore[arg-type]
        repository,
        DummyVault(),
        round17_leo_approver_actor_id=LEO_ID,
    )

    with pytest.raises(SourceServiceRejected, match="staff binding"):
        await service.assign_round17_governance_scheme(
            SOURCE_ID,
            cohort_key="r17-sources-v0.1",
            reason="a name claim alone is not an approval attestation",
            actor_id=LEO_ID,
            actor_display_name="LEO",
            oidc_issuer="https://sso.srbg.cn/realms/internal",
            oidc_subject="leo-subject",
            request_id="round17-unbound-leo",
        )

    assert repository.assignments == []


@pytest.mark.asyncio
async def test_round17_scheme_cannot_be_attached_after_trial_or_with_an_unbounded_key() -> None:
    repository = AssignmentRepository(SourceLifecycleState.TRIAL)
    service = SourceRegistryService(  # type: ignore[arg-type]
        repository,
        DummyVault(),
        round17_leo_approver_actor_id=LEO_ID,
    )

    with pytest.raises(SourceServiceRejected, match="before governance decisions"):
        await service.assign_round17_governance_scheme(
            SOURCE_ID,
            cohort_key="r17-sources-v0.1",
            reason="late assignment must fail closed",
            actor_id=LEO_ID,
            actor_display_name="LEO",
            oidc_issuer="https://sso.srbg.cn/realms/internal",
            oidc_subject="leo-subject",
            request_id="round17-late-assignment",
        )
    with pytest.raises(SourceServiceRejected, match="cohort key"):
        await SourceRegistryService(
            AssignmentRepository(SourceLifecycleState.CANDIDATE),
            DummyVault(),
            round17_leo_approver_actor_id=LEO_ID,
        ).assign_round17_governance_scheme(  # type: ignore[arg-type]
            SOURCE_ID,
            cohort_key="round17-any-source",
            reason="unbounded cohorts are not authoritative",
            actor_id=LEO_ID,
            actor_display_name="LEO",
            oidc_issuer="https://sso.srbg.cn/realms/internal",
            oidc_subject="leo-subject",
            request_id="round17-invalid-cohort",
        )

    assert repository.assignments == []


def test_round17_reuses_only_prior_approvers_and_never_a_maker() -> None:
    makers = frozenset({YINZI_ID})
    prior_approvers = frozenset({LEO_ID, PRIOR_APPROVER_ID})

    assert _governance_separation_actor_ids(
        scheme=ROUND17_TWO_PERSON_GOVERNANCE_SCHEME,
        maker_actor_ids=makers,
        prior_approver_actor_ids=prior_approvers,
    ) == makers
    assert _governance_separation_actor_ids(
        scheme="FOUR_PERSON_SEPARATION_V1",
        maker_actor_ids=makers,
        prior_approver_actor_ids=prior_approvers,
    ) == makers | prior_approvers
    assert _governance_separation_actor_ids(
        scheme="UNKNOWN_UNTRUSTED_SCHEME",
        maker_actor_ids=makers,
        prior_approver_actor_ids=prior_approvers,
    ) == makers | prior_approvers


class AssignmentApiStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def assign_round17_governance_scheme(
        self,
        source_id: UUID,
        *,
        cohort_key: str,
        reason: str,
        actor_id: UUID,
        actor_display_name: str,
        oidc_issuer: str,
        oidc_subject: str,
        request_id: str,
    ) -> None:
        self.calls.append(
            {
                "source_id": source_id,
                "cohort_key": cohort_key,
                "reason": reason,
                "actor_id": actor_id,
                "actor_display_name": actor_display_name,
                "oidc_issuer": oidc_issuer,
                "oidc_subject": oidc_subject,
                "request_id": request_id,
            }
        )


def _controlled_assignment_client(stub: AssignmentApiStub) -> TestClient:
    app = create_app(checkers={}, source_service=stub)
    now = datetime.now(UTC)
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=LEO_ID,
        display_name="LEO",
        roles=frozenset({UserRole.SOURCE_ADMIN}),
        local_identity=False,
        acr="urn:srbg:mfa",
        amr=frozenset({"mfa"}),
        authenticated_at=now,
        oidc_issuer="https://sso.srbg.cn/realms/internal",
        oidc_subject="leo-subject",
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        round17_authority_mode="OIDC",
        oidc_step_up_acr_values=["urn:srbg:mfa"],
        round17_leo_approver_actor_id=LEO_ID,
    )
    return TestClient(app)


def test_round17_assignment_api_is_single_source_fixed_cohort_and_non_local() -> None:
    stub = AssignmentApiStub()
    controlled = _controlled_assignment_client(stub)
    endpoint = f"/api/v1/admin/sources/{SOURCE_ID}/round17-governance-assignment"

    assigned = controlled.post(
        endpoint,
        json={"reason": "LEO approved this source for the bounded Round 17 cohort"},
    )
    forged_cohort = controlled.post(
        endpoint,
        json={
            "reason": "attempt to select a different cohort",
            "cohort_key": "r17-sources-v9.9",
        },
    )
    local = TestClient(create_app(checkers={}, source_service=stub)).post(
        endpoint,
        headers={
            "X-SRBG-Local-Roles": "source_admin",
            "X-SRBG-Local-Step-Up": "true",
        },
        json={"reason": "local identities cannot authorize real sources"},
    )

    assert assigned.status_code == 204
    assert forged_cohort.status_code == 422
    assert local.status_code == 403
    assert len(stub.calls) == 1
    assert stub.calls[0]["source_id"] == SOURCE_ID
    assert stub.calls[0]["cohort_key"] == "r17-sources-v0.1"


@pytest.mark.parametrize("role", [UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN])
def test_round17_assignment_api_rejects_every_other_privileged_actor(role: UserRole) -> None:
    stub = AssignmentApiStub()
    app = create_app(checkers={}, source_service=stub)
    now = datetime.now(UTC)
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=PRIOR_APPROVER_ID,
        display_name="LEO",
        roles=frozenset({role}),
        local_identity=False,
        acr="urn:srbg:mfa",
        amr=frozenset({"mfa"}),
        authenticated_at=now,
        oidc_issuer="https://sso.srbg.cn/realms/internal",
        oidc_subject="other-subject",
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        oidc_step_up_acr_values=["urn:srbg:mfa"],
        round17_leo_approver_actor_id=LEO_ID,
    )

    response = TestClient(app).post(
        f"/api/v1/admin/sources/{SOURCE_ID}/round17-governance-assignment",
        json={"reason": "an ordinary privileged role is insufficient"},
    )

    assert response.status_code == 403
    assert stub.calls == []


def test_round17_assignment_api_fails_closed_without_trusted_leo_actor_attestation() -> None:
    stub = AssignmentApiStub()
    app = create_app(checkers={}, source_service=stub)
    now = datetime.now(UTC)
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=LEO_ID,
        display_name="LEO",
        roles=frozenset({UserRole.SOURCE_ADMIN}),
        local_identity=False,
        acr="urn:srbg:mfa",
        amr=frozenset({"mfa"}),
        authenticated_at=now,
        oidc_issuer="https://sso.srbg.cn/realms/internal",
        oidc_subject="leo-subject",
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        oidc_step_up_acr_values=["urn:srbg:mfa"]
    )

    response = TestClient(app).post(
        f"/api/v1/admin/sources/{SOURCE_ID}/round17-governance-assignment",
        json={"reason": "a missing server attestation must never default to allow"},
    )

    assert response.status_code == 403
    assert stub.calls == []


@pytest.mark.parametrize(
    ("oidc_issuer", "oidc_subject"),
    [
        (None, "leo-subject"),
        ("https://sso.srbg.cn/realms/internal", None),
    ],
)
def test_round17_assignment_api_rejects_missing_signed_oidc_identity_claims(
    oidc_issuer: str | None,
    oidc_subject: str | None,
) -> None:
    stub = AssignmentApiStub()
    app = create_app(checkers={}, source_service=stub)
    now = datetime.now(UTC)
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=LEO_ID,
        display_name="LEO",
        roles=frozenset({UserRole.SOURCE_ADMIN}),
        local_identity=False,
        acr="urn:srbg:mfa",
        amr=frozenset({"mfa"}),
        authenticated_at=now,
        oidc_issuer=oidc_issuer,
        oidc_subject=oidc_subject,
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        oidc_step_up_acr_values=["urn:srbg:mfa"],
        round17_leo_approver_actor_id=LEO_ID,
    )

    response = TestClient(app).post(
        f"/api/v1/admin/sources/{SOURCE_ID}/round17-governance-assignment",
        json={"reason": "unbound OIDC claims cannot authorize source governance"},
    )

    assert response.status_code == 403
    assert stub.calls == []

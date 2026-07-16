from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0017b_round17_pilot.py")


def test_round17_migration_has_immutable_pilot_gold_and_work_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "round17_pilot_window",
        "round17_pilot_window_source",
        "round17_eventization_readiness",
        "round17_gold_task",
        "round17_gold_assignment",
        "round17_gold_annotation",
        "round17_gold_arbitration",
        "round17_gold_release",
        "round17_operator_task",
        "round17_operator_work_session",
        "round17_operator_work_correction",
        "round17_metric_snapshot",
    ):
        assert f'"{table}"' in source
    assert "run_origin" in source
    assert "SCHEDULED','REPLAY','BACKFILL','DRILL" in source
    assert "record_scheduled_source_raw" in source
    assert "record_scheduled_source_document" in source
    assert "0017B_DOWNGRADE_BLOCKED" in source
    assert "srbg_projection_reader" in source
    assert "REVOKE ALL" in source


def test_work_session_schema_cannot_store_content_or_sensitive_notes() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    work_section = source.split('"round17_operator_work_session"', 1)[1].split(
        '"round17_operator_work_correction"', 1
    )[0]
    assert "body" not in work_section.lower()
    assert "content" not in work_section.lower()
    assert "note" not in work_section.lower()
    assert "active_seconds" in work_section
    assert '"window_id"' in work_section
    assert '"last_activity_at"' in work_section
    assert '"accrued_seconds"' in work_section
    assert "round17_pilot_window.id" in work_section
    correction_section = source.split('"round17_operator_work_correction"', 1)[1].split(
        '"round17_metric_snapshot"', 1
    )[0]
    assert '"reason_code"' in correction_section
    assert '"corrected_by"' in correction_section
    assert "actor_id<>corrected_by" in correction_section
    assert '"reason"' not in correction_section
    assert "TIMER_INTERRUPTED" in correction_section


def test_operator_tasks_are_authoritative_and_cannot_be_split_into_sessions() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    task_section = source.split('"round17_operator_task"', 1)[1].split(
        '"round17_operator_work_session"', 1
    )[0]
    session_section = source.split('"round17_operator_work_session"', 1)[1].split(
        '"round17_operator_work_correction"', 1
    )[0]

    for field in (
        '"window_id"',
        '"source_id"',
        '"category"',
        '"assigned_to"',
        '"status"',
        '"created_at"',
        '"started_at"',
        '"completed_at"',
    ):
        assert field in task_section
    assert "body" not in task_section.lower()
    assert "content" not in task_section.lower()
    assert "url" not in task_section.lower()
    assert "note" not in task_section.lower()
    assert '"task_id"' in session_section
    assert "round17_operator_task.id" in session_section
    assert "uq_round17_work_session_task" in session_section
    assert "validate_round17_operator_task" in source
    assert "validate_round17_work_session" in source
    assert "start_round17_operator_task" in source
    assert "complete_round17_operator_task" in source
    assert "operator task may have exactly one execution session" in source
    assert "operator task/session authority mismatch" in source
    role_grants = source.split("def _configure_roles", 1)[1].split("def downgrade", 1)[0]
    assert "ON round17_operator_task TO srbg_api_role" not in "".join(
        line for line in role_grants.splitlines() if "GRANT UPDATE" in line
    )


def test_source_segments_can_start_pause_and_version_without_silent_pin_drift() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "uq_round17_window_source_segment" in source
    assert "uq_round17_window_source_code_segment" in source
    assert "protect_round17_source_segment_pins" in source
    assert "pause_round17_segments_on_source_change" in source
    assert "pause_round17_segments_on_schedule_change" in source
    assert 'sa.Column("resumed_by"' in source
    assert 'sa.Column("resume_request_id"' in source
    assert 'sa.Column("eventization_readiness_id"' in source
    assert "previous source segment must be PAUSED" in source
    assert "current source authority is not eligible for resume" in source
    assert (
        "GRANT UPDATE (status,segment_started_at,segment_ends_at,paused_at,pause_reason)"
        in source
    )
    immutable_loop = source.split("def _create_append_only_boundaries", 1)[1].split(
        "def _create_window_binding_boundary", 1
    )[0]
    assert '"round17_pilot_window_source",' not in immutable_loop


def test_eventization_readiness_is_immutable_profile_pinned_and_never_seeded() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    section = source.split('"round17_eventization_readiness"', 1)[1].split(
        '"round17_pilot_window"', 1
    )[0]

    for profile in (
        "business_parser_profile",
        "claim_evidence_profile",
        "event_identity_profile",
        "publication_projection_profile",
    ):
        assert f'"{profile}_version"' in section
        assert f'"{profile}_sha256"' in section
    assert "status='PASSED'" in section
    assert '"verification_manifest_ref"' in section
    assert '"verification_manifest"' in section
    assert '"verification_signature"' in section
    assert '"signer_public_key_sha256"' in section
    assert "urn:srbg:round17-eventization-manifest" in section
    assert "fk_round17_eventization_verified_staff" in section
    assert "round17-eventization-manifest-v1" in section
    assert "reject_immutable_source_vault_change" in source
    assert "INSERT INTO round17_eventization_readiness" not in source


def test_t0_start_atomically_aligns_authoritative_schedules_to_window_start() -> None:
    service = Path("apps/api/src/srbg_api/operations/service.py").read_text(
        encoding="utf-8"
    )
    start = service.split("async def start_pilot_window", 1)[1].split(
        "async def resume_pilot_source", 1
    )[0]

    assert "FOR UPDATE" in start
    assert "SET next_run_at=:started,updated_at=:started" in start
    assert "schedule_alignment.rowcount != 20" in start


def test_round17_window_has_one_running_instance_and_immutable_state_machine() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "uq_round17_single_running_window" in source
    assert "WHERE state='RUNNING'" in source
    assert "round17 pilot window status transition is invalid" in source
    assert "OLD.started_by IS NOT NULL" in source
    assert "OLD.started_at IS NOT NULL" in source
    assert "OLD.ends_at IS NOT NULL" in source
    assert "state IN ('PREPARING','READY')" in source
    assert "BEFORE INSERT OR UPDATE" in source
    assert "must begin in PREPARING state" in source
    assert "fact changes require a new version" in source
    assert "pilot window cannot complete before ends_at" in source
    assert "pilot window requires 20 honest final source states" in source


def test_operator_work_correction_is_leo_reviewed_and_append_only() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "validate_round17_work_correction" in source
    assert "display_name='LEO'" in source
    assert "responsibility='SOURCE_APPROVER'" in source
    assert "display_name='yinzi'" in source
    assert "responsibility='SOURCE_OPERATOR'" in source
    assert "round17 work correction requires LEO review of yinzi evidence" in source


def test_gold_arbitration_selection_is_bound_to_the_same_task_in_database() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "uq_round17_gold_annotation_task" in source
    assert "fk_round17_arbitration_selected_task" in source
    assert '["selected_annotation_id", "task_id"]' in source


def test_api_cannot_self_provision_oidc_staff_or_eventization_readiness_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    grants = source.split("def _configure_roles", 1)[1].split("def downgrade", 1)[0]

    insert_grants = "".join(
        line.strip() for line in grants.splitlines() if "GRANT INSERT" in line
    )
    assert "round17_staff_binding" not in insert_grants
    assert "round17_eventization_readiness" not in insert_grants


def test_source_pause_is_segment_scoped_and_keeps_the_observation_window_running() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    boundary = source.split("def _create_window_binding_boundary", 1)[1].split(
        "def _create_scheduled_runtime_boundaries", 1
    )[0]

    assert boundary.count("SET status='PAUSED'") == 3
    assert "SET state='BLOCKED'" not in boundary
    assert boundary.count("SET version=version+1") == 3


def test_gold_facts_pin_roster_and_definition_versions_and_separate_digital_duties() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    staff_section = source.split('"round17_staff_binding"', 1)[1].split(
        '"round17_pilot_window"', 1
    )[0]
    task_section = source.split('"round17_gold_task"', 1)[1].split(
        '"round17_gold_assignment"', 1
    )[0]
    release_section = source.split('"round17_gold_release"', 1)[1].split(
        "def _create_work_and_metric_tables", 1
    )[0]

    assert "'DIGITAL_PRIMARY','DIGITAL_SECONDARY'" in staff_section
    for section in (task_section, release_section):
        assert 'sa.Column("roster_version"' in section
        assert 'sa.Column("gold_definition_version"' in section
    assert 'sa.Column("source_codes"' in release_section
    assert "ck_round17_gold_release_source_codes" in release_section


def test_scheduled_runtime_rechecks_lease_window_segment_and_approval_at_statement_time() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    runtime = source.split("def _create_scheduled_runtime_boundaries", 1)[1].split(
        "def _configure_roles", 1
    )[0]

    assert runtime.count("statement_timestamp()") >= 2
    assert runtime.count("run.execution_lease_until>v_now") == 2
    assert runtime.count("segment.status='RUNNING'") == 2
    assert runtime.count("window_row.state='RUNNING'") == 2
    assert runtime.count("v_now>=segment.segment_started_at") == 2
    assert runtime.count("v_now<segment.segment_ends_at") == 2
    assert runtime.count("policy.valid_from<=v_now") == 2
    assert runtime.count("decision.valid_until>v_now") == 2


def test_real_health_anomalies_pause_round17_segments_and_store_only_shape_hashes() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    boundary = source.split("pause_round17_segments_on_anomaly", 1)[1].split(
        "CREATE TRIGGER trg_round17_source_anomaly", 1
    )[0]

    for code in (
        "ZERO_DISCOVERY_STREAK",
        "BODY_LENGTH_SHIFT",
        "REQUIRED_FIELDS_MISSING",
        "DOM_FINGERPRINT_CHANGED",
    ):
        assert code in boundary
    assert '"source_health_snapshot",' in source
    assert '"structure_fingerprint_sha256"' in source
    assert '"discovery_body_bytes"' in source


def test_run_level_physical_request_and_response_totals_are_authoritative_facts() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    scheduling = Path("apps/api/src/srbg_api/scheduling/service.py").read_text(
        encoding="utf-8"
    )

    assert 'sa.Column("request_count"' in migration
    assert 'sa.Column("response_bytes"' in migration
    assert "SET request_count=r.request_count+1" in scheduling
    assert "SET response_bytes=r.response_bytes+:response_bytes" in scheduling
    assert "request_count=request_count+:request_count" not in scheduling
    assert "response_bytes=response_bytes+:response_bytes" not in scheduling

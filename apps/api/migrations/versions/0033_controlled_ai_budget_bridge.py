# ruff: noqa: E501
"""Atomically bridge controlled-run cost limits to the existing AI budget ledger.

Revision ID: 0033_controlled_ai_budget_bridge
Revises: 0032_controlled_run_worker_read
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_controlled_ai_budget_bridge"
down_revision = "0032_controlled_run_worker_read"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_ai_budget_step", "ai_budget_reservation", type_="check")
    op.create_check_constraint(
        "ck_ai_budget_step",
        "ai_budget_reservation",
        "step IN ('CLASSIFY','EXTRACT','SUMMARIZE','VERIFY')",
    )
    op.add_column(
        "ai_budget_reservation",
        sa.Column(
            "controlled_run_id",
            _uuid(),
            sa.ForeignKey("personal_controlled_run.id", ondelete="RESTRICT"),
        ),
    )
    op.add_column(
        "ai_budget_reservation",
        sa.Column("controlled_cost_reserved_microusd", sa.BigInteger()),
    )
    op.add_column(
        "ai_budget_reservation",
        sa.Column("controlled_cost_settled_microusd", sa.BigInteger()),
    )
    op.create_check_constraint(
        "ck_ai_budget_controlled_cost_bridge",
        "ai_budget_reservation",
        "(controlled_run_id IS NULL AND controlled_cost_reserved_microusd IS NULL "
        "AND controlled_cost_settled_microusd IS NULL) OR "
        "(controlled_run_id IS NOT NULL AND controlled_cost_reserved_microusd > 0 "
        "AND (controlled_cost_settled_microusd IS NULL OR "
        "controlled_cost_settled_microusd BETWEEN 0 AND controlled_cost_reserved_microusd))",
    )
    op.execute(_RESERVE_CONTROLLED_AI)
    op.execute(_SETTLE_CONTROLLED_AI)
    op.execute(_RELEASE_CONTROLLED_AI)
    for signature in (
        "reserve_controlled_ai_budget(uuid,uuid,text,integer,integer,bigint,timestamptz)",
        "settle_controlled_ai_budget(uuid,bigint,text,timestamptz)",
        "release_controlled_ai_budget(uuid,timestamptz)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_worker_role")


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM ai_budget_reservation "
            "WHERE controlled_run_id IS NOT NULL OR billing_status='RESERVED' "
            "AND controlled_cost_reserved_microusd IS NOT NULL)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError(
            "CONTROLLED_AI_BRIDGE_DOWNGRADE_BLOCKED: controlled AI budget facts exist"
        )
    for signature in (
        "release_controlled_ai_budget(uuid,timestamptz)",
        "settle_controlled_ai_budget(uuid,bigint,text,timestamptz)",
        "reserve_controlled_ai_budget(uuid,uuid,text,integer,integer,bigint,timestamptz)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.drop_constraint(
        "ck_ai_budget_controlled_cost_bridge", "ai_budget_reservation", type_="check"
    )
    op.drop_column("ai_budget_reservation", "controlled_cost_settled_microusd")
    op.drop_column("ai_budget_reservation", "controlled_cost_reserved_microusd")
    op.drop_column("ai_budget_reservation", "controlled_run_id")
    op.drop_constraint("ck_ai_budget_step", "ai_budget_reservation", type_="check")
    op.create_check_constraint(
        "ck_ai_budget_step",
        "ai_budget_reservation",
        "step IN ('CLASSIFY','EXTRACT')",
    )


_RESERVE_CONTROLLED_AI = r"""
CREATE FUNCTION reserve_controlled_ai_budget(
  p_reservation_id uuid,p_pipeline_run_id uuid,p_step text,p_attempt integer,
  p_requested_points integer,p_reserved_cost_microusd bigint,p_now timestamptz
) RETURNS TABLE(reservation_id uuid,alert_crossed boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE v_run personal_controlled_run%ROWTYPE; v_policy ai_budget_policy%ROWTYPE;
        v_month date; v_document_total integer; v_alert boolean; v_existing ai_budget_reservation%ROWTYPE;
BEGIN
  IF substring(p_reservation_id::text,15,1)<>'7' OR p_step NOT IN ('CLASSIFY','EXTRACT','SUMMARIZE','VERIFY')
     OR p_attempt NOT BETWEEN 1 AND 4 OR p_requested_points NOT BETWEEN 1 AND 100
     OR p_reserved_cost_microusd<=0
     OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes' AND clock_timestamp()+interval '5 minutes'
  THEN RAISE EXCEPTION 'CONTROLLED_AI_BUDGET_INPUT_INVALID'; END IF;
  SELECT controlled.* INTO v_run FROM ai_pipeline_run pipeline
    JOIN personal_controlled_run controlled ON controlled.id=pipeline.controlled_run_id
   WHERE pipeline.id=p_pipeline_run_id FOR UPDATE OF controlled;
  IF NOT FOUND OR v_run.state<>'RUNNING' THEN RAISE EXCEPTION 'CONTROLLED_AI_RUN_NOT_RUNNING'; END IF;
  SELECT * INTO v_existing FROM ai_budget_reservation
   WHERE pipeline_run_id=p_pipeline_run_id AND step=p_step AND attempt=p_attempt;
  IF FOUND THEN
    IF v_existing.controlled_run_id<>v_run.id THEN RAISE EXCEPTION 'CONTROLLED_AI_RESERVATION_CONFLICT'; END IF;
    RETURN QUERY SELECT v_existing.id,false; RETURN;
  END IF;
  IF v_run.ai_cost_reserved_microusd+v_run.ai_cost_settled_microusd+p_reserved_cost_microusd
       >v_run.ai_cost_limit_microusd THEN RAISE EXCEPTION 'CONTROLLED_AI_COST_LIMIT'; END IF;
  SELECT * INTO v_policy FROM ai_budget_policy
   WHERE provider='deepseek' AND model='deepseek-v4-flash' AND active FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'MODEL_DISABLED'; END IF;
  v_month:=date_trunc('month',p_now AT TIME ZONE 'UTC')::date;
  INSERT INTO ai_budget_month(policy_id,month_start) VALUES(v_policy.id,v_month) ON CONFLICT DO NOTHING;
  PERFORM 1 FROM ai_budget_month WHERE policy_id=v_policy.id AND month_start=v_month FOR UPDATE;
  SELECT COALESCE(sum(reserved_points),0) INTO v_document_total FROM ai_budget_reservation
   WHERE pipeline_run_id=p_pipeline_run_id AND billing_status IN ('RESERVED','SETTLED','UNKNOWN');
  IF v_document_total+p_requested_points>v_policy.document_points THEN RAISE EXCEPTION 'AI_DOCUMENT_BUDGET_EXCEEDED'; END IF;
  IF (SELECT reserved_points+settled_points FROM ai_budget_month WHERE policy_id=v_policy.id AND month_start=v_month)
       +p_requested_points>v_policy.monthly_points THEN RAISE EXCEPTION 'AI_MONTHLY_BUDGET_EXCEEDED'; END IF;
  INSERT INTO ai_budget_reservation(
    id,policy_id,pipeline_run_id,step,attempt,month_start,reserved_points,billing_status,created_at,
    controlled_run_id,controlled_cost_reserved_microusd
  ) VALUES(
    p_reservation_id,v_policy.id,p_pipeline_run_id,p_step,p_attempt,v_month,p_requested_points,
    'RESERVED',p_now,v_run.id,p_reserved_cost_microusd
  );
  UPDATE ai_budget_month SET reserved_points=reserved_points+p_requested_points,
    alerted_at=CASE WHEN alerted_at IS NULL AND reserved_points+settled_points+p_requested_points>=v_policy.alert_points
                    THEN p_now ELSE alerted_at END
   WHERE policy_id=v_policy.id AND month_start=v_month RETURNING alerted_at=p_now INTO v_alert;
  UPDATE personal_controlled_run SET
    ai_cost_reserved_microusd=ai_cost_reserved_microusd+p_reserved_cost_microusd,updated_at=p_now
   WHERE id=v_run.id;
  reservation_id:=p_reservation_id; alert_crossed:=v_alert; RETURN NEXT;
END $$
"""

_SETTLE_CONTROLLED_AI = r"""
CREATE FUNCTION settle_controlled_ai_budget(
  p_reservation_id uuid,p_cost_microusd bigint,p_billing_status text,p_now timestamptz
) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE v_res ai_budget_reservation%ROWTYPE; v_policy ai_budget_policy%ROWTYPE;
        v_points integer; v_charged bigint;
BEGIN
  IF p_cost_microusd<0 OR p_billing_status NOT IN ('SETTLED','UNKNOWN')
  THEN RAISE EXCEPTION 'CONTROLLED_AI_SETTLEMENT_INVALID'; END IF;
  SELECT * INTO v_res FROM ai_budget_reservation WHERE id=p_reservation_id FOR UPDATE;
  IF NOT FOUND OR v_res.controlled_run_id IS NULL THEN RAISE EXCEPTION 'CONTROLLED_AI_RESERVATION_MISSING'; END IF;
  IF v_res.controlled_cost_settled_microusd IS NOT NULL THEN RETURN COALESCE(v_res.settled_points,v_res.reserved_points); END IF;
  IF p_billing_status='SETTLED' AND p_cost_microusd>v_res.controlled_cost_reserved_microusd
  THEN RAISE EXCEPTION 'CONTROLLED_AI_RESERVATION_UNDERSIZED'; END IF;
  SELECT * INTO v_policy FROM ai_budget_policy WHERE id=v_res.policy_id;
  v_points:=CASE WHEN p_billing_status='UNKNOWN' THEN v_res.reserved_points
                 ELSE ceiling(p_cost_microusd*v_policy.points_per_usd/1000000.0)::integer END;
  IF v_points>v_res.reserved_points THEN RAISE EXCEPTION 'AI_BUDGET_RESERVATION_UNDERSIZED'; END IF;
  v_charged:=CASE WHEN p_billing_status='UNKNOWN' THEN v_res.controlled_cost_reserved_microusd ELSE p_cost_microusd END;
  UPDATE ai_budget_reservation SET settled_points=v_points,
    cost_microusd=CASE WHEN p_billing_status='SETTLED' THEN p_cost_microusd END,
    billing_status=p_billing_status,settled_at=p_now,controlled_cost_settled_microusd=v_charged
   WHERE id=p_reservation_id;
  UPDATE ai_budget_month SET reserved_points=reserved_points-v_res.reserved_points,
    settled_points=settled_points+v_points WHERE policy_id=v_res.policy_id AND month_start=v_res.month_start;
  UPDATE personal_controlled_run SET
    ai_cost_reserved_microusd=ai_cost_reserved_microusd-v_res.controlled_cost_reserved_microusd,
    ai_cost_settled_microusd=ai_cost_settled_microusd+v_charged,updated_at=p_now
   WHERE id=v_res.controlled_run_id;
  RETURN v_points;
END $$
"""

_RELEASE_CONTROLLED_AI = r"""
CREATE FUNCTION release_controlled_ai_budget(p_reservation_id uuid,p_now timestamptz)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE v_res ai_budget_reservation%ROWTYPE;
BEGIN
  SELECT * INTO v_res FROM ai_budget_reservation WHERE id=p_reservation_id FOR UPDATE;
  IF NOT FOUND OR v_res.controlled_run_id IS NULL THEN RAISE EXCEPTION 'CONTROLLED_AI_RESERVATION_MISSING'; END IF;
  IF v_res.billing_status<>'RESERVED' THEN RETURN COALESCE(v_res.settled_points,v_res.reserved_points); END IF;
  UPDATE ai_budget_reservation SET settled_points=0,billing_status='RELEASED',settled_at=p_now,
    controlled_cost_settled_microusd=0 WHERE id=p_reservation_id;
  UPDATE ai_budget_month SET reserved_points=reserved_points-v_res.reserved_points
   WHERE policy_id=v_res.policy_id AND month_start=v_res.month_start;
  UPDATE personal_controlled_run SET
    ai_cost_reserved_microusd=ai_cost_reserved_microusd-v_res.controlled_cost_reserved_microusd,updated_at=p_now
   WHERE id=v_res.controlled_run_id;
  RETURN 0;
END $$
"""

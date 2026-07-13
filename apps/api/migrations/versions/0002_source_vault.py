# ruff: noqa: RUF001
"""Add the source registry and immutable raw-document vault.

Revision ID: 0002_source_vault
Revises: 0001_foundation
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_source_vault"
down_revision: str | Sequence[str] | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())
SOURCE_STATES = (
    "CANDIDATE",
    "COMPLIANCE_REVIEW",
    "FIXTURE_TEST",
    "APPROVED",
    "ACTIVE",
)
SOURCE_STATE_SQL = "','".join(SOURCE_STATES)

# The checked-in registry is deliberately copied into the migration so a production
# image can migrate without depending on the documentation tree.
SEED_SOURCES = (
    (
        "GOV-001",
        "国家法律法规数据库",
        "https://flk.npc.gov.cn/",
        "SAFETY",
        "government",
        "A0",
        "P0",
        "public_search",
        1440,
    ),
    (
        "GOV-002",
        "中国政府网政策",
        "https://www.gov.cn/zhengce/",
        "BOTH",
        "government",
        "A1",
        "P0",
        "html",
        60,
    ),
    (
        "GOV-003",
        "交通运输部",
        "https://www.mot.gov.cn/",
        "BOTH",
        "government",
        "A1",
        "P0",
        "html",
        30,
    ),
    (
        "GOV-004",
        "交通运输部政府信息公开",
        "https://xxgk.mot.gov.cn/",
        "BOTH",
        "government",
        "A1",
        "P0",
        "html_pdf",
        30,
    ),
    (
        "GOV-005",
        "住房和城乡建设部",
        "https://www.mohurd.gov.cn/",
        "BOTH",
        "government",
        "A1",
        "P0",
        "html_pdf",
        30,
    ),
    (
        "GOV-006",
        "应急管理部",
        "https://www.mem.gov.cn/",
        "SAFETY",
        "government",
        "A1",
        "P0",
        "html_pdf",
        15,
    ),
    (
        "GOV-007",
        "应急管理部事故调查报告",
        "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/",
        "SAFETY",
        "government",
        "A0",
        "P0",
        "html_pdf",
        15,
    ),
    (
        "GOV-008",
        "全国标准信息公共服务平台",
        "https://std.samr.gov.cn/",
        "SAFETY",
        "standards",
        "A0",
        "P0",
        "public_search",
        1440,
    ),
    (
        "GOV-009",
        "国家标准全文公开系统",
        "https://openstd.samr.gov.cn/",
        "SAFETY",
        "standards",
        "A0",
        "P1",
        "public_search",
        1440,
    ),
    (
        "GOV-010",
        "工业和信息化部",
        "https://www.miit.gov.cn/",
        "DIGITAL",
        "government",
        "A1",
        "P1",
        "html_pdf",
        120,
    ),
    (
        "GOV-011",
        "国务院国资委",
        "https://www.sasac.gov.cn/",
        "DIGITAL",
        "government",
        "A1",
        "P1",
        "html",
        120,
    ),
    (
        "GOV-012",
        "国家发展改革委",
        "https://www.ndrc.gov.cn/",
        "DIGITAL",
        "government",
        "A1",
        "P1",
        "html_pdf",
        120,
    ),
    (
        "GOV-013",
        "科学技术部",
        "https://www.most.gov.cn/",
        "DIGITAL",
        "government",
        "A1",
        "P2",
        "html",
        1440,
    ),
    (
        "GOV-014",
        "中国民用航空局",
        "https://www.caac.gov.cn/",
        "DIGITAL",
        "government",
        "A1",
        "P1",
        "html_pdf",
        120,
    ),
    (
        "GOV-015",
        "四川省交通运输厅",
        "https://jtt.sc.gov.cn/",
        "BOTH",
        "government",
        "A1",
        "P0",
        "html_pdf",
        30,
    ),
    (
        "GOV-016",
        "四川省应急管理厅",
        "https://yjt.sc.gov.cn/",
        "SAFETY",
        "government",
        "A1",
        "P0",
        "html_pdf",
        15,
    ),
    (
        "GOV-017",
        "四川省住房和城乡建设厅",
        "https://jst.sc.gov.cn/",
        "BOTH",
        "government",
        "A1",
        "P0",
        "html_pdf",
        30,
    ),
    (
        "GOV-018",
        "四川省市场监督管理局",
        "https://scjgj.sc.gov.cn/",
        "SAFETY",
        "government",
        "A1",
        "P1",
        "html_pdf",
        1440,
    ),
    (
        "RES-001",
        "中国公路学会",
        "https://www.chts.cn/",
        "DIGITAL",
        "association",
        "B1",
        "P0",
        "html",
        120,
    ),
    (
        "RES-002",
        "中国施工企业管理协会",
        "https://www.cacem.com.cn/",
        "DIGITAL",
        "association",
        "B1",
        "P0",
        "html_pdf",
        1440,
    ),
    (
        "RES-003",
        "中国建筑科学研究院",
        "https://www.cabr.com.cn/",
        "DIGITAL",
        "research_institute",
        "B1",
        "P1",
        "html",
        1440,
    ),
    (
        "RES-004",
        "中国公路学报",
        "https://zgglxb.chd.edu.cn/",
        "DIGITAL",
        "journal",
        "B1",
        "P0",
        "rss_or_html",
        1440,
    ),
    (
        "RES-005",
        "隧道建设（中英文）",
        "http://www.suidaojs.com/",
        "DIGITAL",
        "journal",
        "B1",
        "P0",
        "rss_or_html",
        1440,
    ),
    (
        "RES-006",
        "中国安全科学学报",
        "http://www.cssjj.com.cn/CN/1003-3033/home.shtml",
        "SAFETY",
        "journal",
        "B1",
        "P0",
        "rss_or_html",
        1440,
    ),
    (
        "RES-007",
        "OpenAlex API",
        "https://developers.openalex.org/",
        "DIGITAL",
        "academic_api",
        "B1",
        "P0",
        "api",
        1440,
    ),
    (
        "RES-008",
        "Crossref REST API",
        "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        "DIGITAL",
        "academic_api",
        "B1",
        "P0",
        "api",
        1440,
    ),
    (
        "RES-009",
        "中国知网",
        "https://www.cnki.net/",
        "DIGITAL",
        "academic_database",
        "B1",
        "P1",
        "licensed_api_or_manual",
        1440,
    ),
    (
        "RES-010",
        "万方数据",
        "https://www.wanfangdata.com.cn/",
        "DIGITAL",
        "academic_database",
        "B1",
        "P1",
        "licensed_api_or_manual",
        1440,
    ),
    (
        "RES-011",
        "中国土木工程学会",
        "https://www.cces.net.cn/",
        "DIGITAL",
        "association",
        "B1",
        "P1",
        "html",
        1440,
    ),
    (
        "RES-012",
        "中国建筑业协会",
        "https://www.zgjzy.org.cn/",
        "DIGITAL",
        "association",
        "B1",
        "P1",
        "html",
        1440,
    ),
    (
        "ENT-001",
        "中国交建",
        "https://www.ccccltd.cn/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P0",
        "html",
        240,
    ),
    (
        "ENT-002",
        "中国建筑",
        "https://www.cscec.com/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P1",
        "html",
        240,
    ),
    (
        "ENT-003",
        "中国中铁",
        "https://www.crecg.com/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P0",
        "html",
        240,
    ),
    (
        "ENT-004",
        "中国铁建",
        "https://www.crcc.cn/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P0",
        "html",
        240,
    ),
    (
        "ENT-005",
        "蜀道集团",
        "https://www.shudaojt.com/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P0",
        "html",
        120,
    ),
    (
        "ENT-006",
        "华为行业数字化",
        "https://e.huawei.com/cn/industries/transportation",
        "DIGITAL",
        "enterprise",
        "B2",
        "P1",
        "html",
        1440,
    ),
    (
        "ENT-007",
        "广联达",
        "https://www.glodon.com/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P0",
        "html",
        1440,
    ),
    (
        "ENT-008",
        "大疆行业应用",
        "https://enterprise.dji.com/cn",
        "DIGITAL",
        "enterprise",
        "B2",
        "P0",
        "html",
        1440,
    ),
    (
        "ENT-009",
        "三一集团",
        "https://www.sanygroup.com/",
        "DIGITAL",
        "enterprise",
        "B2",
        "P1",
        "html",
        1440,
    ),
    (
        "MED-001",
        "中国公路网",
        "https://www.chinahighway.com/",
        "DIGITAL",
        "media",
        "C1",
        "P1",
        "rss_or_html",
        60,
    ),
    (
        "MED-002",
        "科技日报",
        "https://www.stdaily.com/",
        "DIGITAL",
        "media",
        "C1",
        "P1",
        "rss_or_html",
        60,
    ),
    (
        "MED-003",
        "Engineering News-Record",
        "https://www.enr.com/",
        "BOTH",
        "media",
        "C1",
        "P2",
        "rss_or_html",
        1440,
    ),
)


def _uuid7_seed(sequence: int) -> UUID:
    return UUID(f"019b0000-0000-7000-8000-{sequence:012d}")


def upgrade() -> None:
    now = datetime.now(UTC)
    op.create_table(
        "source",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("registry_code", sa.String(30), unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("authority_level", sa.String(2), nullable=False),
        sa.Column("priority", sa.String(2), nullable=False),
        sa.Column("collection_method", sa.String(50), nullable=False),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("state", sa.String(30), nullable=False, server_default="CANDIDATE"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"state IN ('{SOURCE_STATE_SQL}')",
            name="ck_source_state",
        ),
        sa.CheckConstraint("channel IN ('DIGITAL','SAFETY','BOTH')", name="ck_source_channel"),
        sa.CheckConstraint(
            "poll_interval_minutes BETWEEN 1 AND 10080", name="ck_source_poll_interval"
        ),
    )
    op.create_index("ix_source_state_enabled", "source", ["state", "enabled"])

    op.create_table(
        "source_policy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("source.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("document", JSON, nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "policy_version", name="uq_source_policy_version"),
        sa.CheckConstraint(
            "status IN ('DRAFT','VALID','EXPIRED','REVOKED')", name="ck_source_policy_status"
        ),
    )
    op.create_index("ix_source_policy_source_created", "source_policy", ["source_id", "created_at"])

    op.create_table(
        "source_connector",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("source.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column("config", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", name="uq_source_connector_source"),
    )

    op.create_table(
        "raw_object",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("object_key", sa.String(255), nullable=False, unique=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("declared_mime", sa.String(100), nullable=False),
        sa.Column("detected_mime", sa.String(100), nullable=False),
        sa.Column("scan_status", sa.String(20), nullable=False),
        sa.Column("storage_etag", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size >= 0", name="ck_raw_object_size"),
        sa.CheckConstraint("scan_status IN ('CLEAN','REJECTED')", name="ck_raw_object_scan_status"),
    )

    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("document_kind", sa.String(10), nullable=False),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_version_id", sa.Uuid()),
        sa.UniqueConstraint("source_id", "canonical_url", name="uq_document_source_url"),
        sa.CheckConstraint("document_kind IN ('HTML','PDF')", name="ck_document_kind"),
    )
    op.create_table(
        "document_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("document.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_object_id",
            sa.Uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        sa.UniqueConstraint("document_id", "content_hash", name="uq_document_content_hash"),
        sa.CheckConstraint("version_number > 0", name="ck_document_version_positive"),
    )
    op.create_foreign_key(
        "fk_document_current_version",
        "document",
        "document_version",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_document_version_document_acquired", "document_version", ["document_id", "acquired_at"]
    )

    op.create_table(
        "document_attachment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            sa.Uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_object_id",
            sa.Uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="FIXTURE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "source_onboarding_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("source.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "source_policy_id",
            sa.Uuid(),
            sa.ForeignKey("source_policy.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("record", JSON, nullable=False),
        sa.Column("record_sha256", sa.String(64), nullable=False),
        sa.Column("fixture_count", sa.Integer(), nullable=False),
        sa.Column("fixture_set_sha256", sa.String(64)),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fixture_count >= 0", name="ck_onboarding_fixture_count"),
    )
    op.create_index(
        "ix_onboarding_source_created", "source_onboarding_record", ["source_id", "created_at"]
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("before_state", JSON),
        sa.Column("after_state", JSON),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("previous_hash", sa.String(64)),
        sa.Column("entry_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_audit_log_target_created", "audit_log", ["target_type", "target_id", "created_at"]
    )

    source_table = sa.table(
        "source",
        sa.column("id", sa.Uuid()),
        sa.column("registry_code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("base_url", sa.String()),
        sa.column("channel", sa.String()),
        sa.column("source_type", sa.String()),
        sa.column("authority_level", sa.String()),
        sa.column("priority", sa.String()),
        sa.column("collection_method", sa.String()),
        sa.column("poll_interval_minutes", sa.Integer()),
        sa.column("owner", sa.String()),
        sa.column("state", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        source_table,
        [
            {
                "id": _uuid7_seed(index),
                "registry_code": row[0],
                "name": row[1],
                "base_url": row[2],
                "channel": row[3],
                "source_type": row[4],
                "authority_level": row[5],
                "priority": row[6],
                "collection_method": row[7],
                "poll_interval_minutes": row[8],
                "owner": "source_ops",
                "state": "CANDIDATE",
                "enabled": False,
                "created_at": now,
                "updated_at": now,
            }
            for index, row in enumerate(SEED_SOURCES, start=1)
        ],
    )

    op.execute(
        """
        CREATE FUNCTION reject_immutable_source_vault_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table_name in (
        "raw_object",
        "document_version",
        "document_attachment",
        "source_policy",
        "source_onboarding_record",
        "audit_log",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change();
            """
        )


def downgrade() -> None:
    for table_name in (
        "audit_log",
        "source_onboarding_record",
        "source_policy",
        "document_attachment",
        "document_version",
        "raw_object",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS reject_immutable_source_vault_change()")
    op.drop_table("audit_log")
    op.drop_table("source_onboarding_record")
    op.drop_table("document_attachment")
    op.drop_constraint("fk_document_current_version", "document", type_="foreignkey")
    op.drop_index("ix_document_version_document_acquired", table_name="document_version")
    op.drop_table("document_version")
    op.drop_table("document")
    op.drop_table("raw_object")
    op.drop_table("source_connector")
    op.drop_index("ix_source_policy_source_created", table_name="source_policy")
    op.drop_table("source_policy")
    op.drop_index("ix_source_state_enabled", table_name="source")
    op.drop_table("source")

"""Add the rebuildable read model used to enforce Owner Feed suppression.

Revision ID: 0052_feed_suppression_projection
Revises: 0051_technical_exception_recovery
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0052_feed_suppression_projection"
down_revision = "0051_technical_exception_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CUSTOM_TOPIC_SPACES = re.compile(r"\s+")


def _canonical_custom_topic(value: str) -> str | None:
    normalized = _CUSTOM_TOPIC_SPACES.sub(
        "-", unicodedata.normalize("NFKC", value.strip()).casefold()
    )
    if (
        not normalized
        or len(normalized) > 300
        or any(unicodedata.category(char) == "Cc" for char in normalized)
    ):
        return None
    return normalized


def _uuid() -> sa.Uuid:
    return sa.Uuid()


def _create_media_reader_view(*, include_event_id: bool) -> None:
    if include_event_id:
        op.execute(
            """
            CREATE VIEW media_delivery_reader_v2 WITH (security_barrier=true) AS
            SELECT binding.event_id,media.id,media.document_version_id,media.name,
              media.object_key,media.source_url,media.mime_type,media.rights_basis,
              media.redistribution_allowed,media.scan_status,
              attachment.security_status AS attachment_scan_status,
              raw.scan_status AS raw_scan_status,media.preview_object_key,
              media.preview_mime_type,media.created_at
            FROM media_rights_v2 media
            JOIN document_version version ON version.id=media.document_version_id
            JOIN intelligence_item item ON item.primary_document_id=version.document_id
            JOIN event_identity_binding binding ON binding.item_id=item.id
            JOIN document_attachment attachment ON attachment.id=media.attachment_id
            JOIN raw_object raw ON raw.id=attachment.raw_object_id
            """
        )
    else:
        op.execute(
            """
            CREATE VIEW media_delivery_reader_v2 WITH (security_barrier=true) AS
            SELECT media.id,media.document_version_id,media.name,media.object_key,
          media.source_url,media.mime_type,media.rights_basis,
          media.redistribution_allowed,media.scan_status,
          attachment.security_status AS attachment_scan_status,
          raw.scan_status AS raw_scan_status,media.preview_object_key,
          media.preview_mime_type,media.created_at
            FROM media_rights_v2 media
            JOIN document_attachment attachment ON attachment.id=media.attachment_id
            JOIN raw_object raw ON raw.id=attachment.raw_object_id
            """
        )
    op.execute(
        "GRANT SELECT ON media_delivery_reader_v2 TO srbg_projection_reader,"
        "srbg_publication_writer"
    )


def upgrade() -> None:
    op.create_table(
        "event_suppression_match_v2",
        sa.Column(
            "event_id",
            _uuid(),
            sa.ForeignKey("event.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("target_key", sa.String(300), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "event_id", "scope", "target_key", name="pk_event_suppression_match_v2"
        ),
        sa.CheckConstraint(
            "scope IN ('EVENT','PRIMARY_TYPE','ENGINEERING_OBJECT','SPECIALTY_FACET',"
            "'EQUIPMENT_DOMAIN','SOURCE','CUSTOM_TOPIC')",
            name="ck_event_suppression_match_scope_v2",
        ),
    )
    op.create_index(
        "ix_event_suppression_match_target_v2",
        "event_suppression_match_v2",
        ["scope", "target_key", "event_id"],
    )
    op.create_index(
        "ix_event_suppression_match_document_v2",
        "event_suppression_match_v2",
        ["document_version_id"],
    )
    op.create_index(
        "uq_feed_suppression_single_revoke_v2",
        "feed_suppression_rule_v2",
        ["supersedes_rule_id"],
        unique=True,
        postgresql_where=sa.text("action='REVOKE'"),
    )
    op.execute(
        """
        CREATE VIEW feed_suppression_effective_v2 WITH (security_barrier=true) AS
        SELECT activation.id,activation.scope,activation.target_key,
          activation.feedback_reason,activation.owner_id,activation.effective_at,
          activation.created_at,revoke.id AS revoke_rule_id,
          revoke.effective_at AS revoked_at
        FROM feed_suppression_rule_v2 activation
        LEFT JOIN feed_suppression_rule_v2 revoke
          ON revoke.action='REVOKE'
         AND revoke.supersedes_rule_id=activation.id
        WHERE activation.action='ACTIVATE'
        """
    )
    op.execute("REVOKE ALL ON event_suppression_match_v2 FROM PUBLIC")
    op.execute("REVOKE ALL ON feed_suppression_effective_v2 FROM PUBLIC")
    op.execute(
        "GRANT SELECT ON event_suppression_match_v2 TO srbg_projection_reader,"
        "srbg_publication_writer"
    )
    op.execute(
        "GRANT INSERT,UPDATE,DELETE ON event_suppression_match_v2 "
        "TO srbg_publication_writer"
    )
    op.execute(
        "GRANT SELECT ON feed_suppression_effective_v2 TO srbg_projection_reader,"
        "srbg_publication_writer"
    )
    op.execute(
        "GRANT INSERT ON feed_suppression_rule_v2 TO srbg_publication_writer"
    )
    op.execute(
        """
        INSERT INTO event_suppression_match_v2(
          event_id,document_version_id,scope,target_key,projected_at
        )
        SELECT projection.event_id,projection.document_version_id,'EVENT',
          projection.event_id::text,projection.projected_at
        FROM intelligence_projection_v2 projection
        UNION ALL
        SELECT projection.event_id,projection.document_version_id,'PRIMARY_TYPE',
          projection.primary_type,projection.projected_at
        FROM intelligence_projection_v2 projection
        UNION ALL
        SELECT projection.event_id,projection.document_version_id,'SOURCE',
          item.source_id::text,projection.projected_at
        FROM intelligence_projection_v2 projection
        JOIN event_identity_binding binding ON binding.event_id=projection.event_id
        JOIN intelligence_item item ON item.id=binding.item_id
        UNION ALL
        SELECT projection.event_id,projection.document_version_id,'ENGINEERING_OBJECT',
          value,projection.projected_at
        FROM intelligence_projection_v2 projection
        JOIN qualification_acceptance_v2 qualification
          ON qualification.event_id=projection.event_id
         AND qualification.document_version_id=projection.document_version_id
        CROSS JOIN LATERAL unnest(qualification.engineering_objects) value
        UNION ALL
        SELECT projection.event_id,projection.document_version_id,'SPECIALTY_FACET',
          value,projection.projected_at
        FROM intelligence_projection_v2 projection
        JOIN qualification_acceptance_v2 qualification
          ON qualification.event_id=projection.event_id
         AND qualification.document_version_id=projection.document_version_id
        CROSS JOIN LATERAL unnest(qualification.specialty_facets) value
        UNION ALL
        SELECT projection.event_id,projection.document_version_id,'EQUIPMENT_DOMAIN',
          value,projection.projected_at
        FROM intelligence_projection_v2 projection
        JOIN qualification_acceptance_v2 qualification
          ON qualification.event_id=projection.event_id
         AND qualification.document_version_id=projection.document_version_id
        CROSS JOIN LATERAL unnest(qualification.equipment_domains) value
        ON CONFLICT DO NOTHING
        """
    )
    connection = op.get_bind()
    custom_topics = connection.execute(
        sa.text(
            "SELECT projection.event_id,projection.document_version_id,"
            "projection.projected_at,topic.title FROM intelligence_projection_v2 projection "
            "JOIN topic_event membership ON membership.event_id=projection.event_id "
            "JOIN topic_cluster topic ON topic.id=membership.topic_id "
            "WHERE topic.status='CONFIRMED'"
        )
    ).mappings()
    custom_topic_rows = []
    for row in custom_topics:
        target_key = _canonical_custom_topic(str(row["title"]))
        if target_key is not None:
            custom_topic_rows.append(
                {
                    "event_id": row["event_id"],
                    "document_version_id": row["document_version_id"],
                    "target_key": target_key,
                    "projected_at": row["projected_at"],
                }
            )
    if custom_topic_rows:
        connection.execute(
            sa.text(
                "INSERT INTO event_suppression_match_v2("
                "event_id,document_version_id,scope,target_key,projected_at) VALUES("
                ":event_id,:document_version_id,'CUSTOM_TOPIC',:target_key,:projected_at) "
                "ON CONFLICT DO NOTHING"
            ),
            custom_topic_rows,
        )
    op.execute(
        """
        CREATE VIEW visible_intelligence_projection_v2 WITH (security_barrier=true) AS
        SELECT projection.*
        FROM intelligence_projection_v2 projection
        WHERE NOT EXISTS (
          SELECT 1
          FROM event_suppression_match_v2 match
          JOIN feed_suppression_effective_v2 rule
            ON rule.scope=match.scope AND rule.target_key=match.target_key
          WHERE match.event_id=projection.event_id
            AND (rule.revoked_at IS NULL OR projection.projected_at<=rule.revoked_at)
        )
        """
    )
    op.execute("REVOKE ALL ON visible_intelligence_projection_v2 FROM PUBLIC")
    op.execute(
        "GRANT SELECT ON visible_intelligence_projection_v2 TO srbg_projection_reader,"
        "srbg_publication_writer"
    )

    op.execute("DROP VIEW IF EXISTS media_delivery_reader_v2")
    _create_media_reader_view(include_event_id=True)


def downgrade() -> None:
    op.execute(
        "REVOKE INSERT ON feed_suppression_rule_v2 FROM srbg_publication_writer"
    )
    op.execute("DROP VIEW IF EXISTS media_delivery_reader_v2")
    _create_media_reader_view(include_event_id=False)
    op.execute("DROP VIEW IF EXISTS visible_intelligence_projection_v2")
    op.execute("DROP VIEW IF EXISTS feed_suppression_effective_v2")
    op.drop_index(
        "uq_feed_suppression_single_revoke_v2",
        table_name="feed_suppression_rule_v2",
    )
    op.drop_index(
        "ix_event_suppression_match_document_v2",
        table_name="event_suppression_match_v2",
    )
    op.drop_index(
        "ix_event_suppression_match_target_v2",
        table_name="event_suppression_match_v2",
    )
    op.drop_table("event_suppression_match_v2")

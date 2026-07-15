"""TEST-only PostgreSQL fixture statements for Round 14 reconciliation evidence."""

INSERT_PUBLICATION = """
    INSERT INTO publication (id,item_id,status,published_at,updated_at)
    VALUES (:publication,:item,'PUBLISHED',now(),now())
"""

INSERT_PUBLICATION_REVISION = """
    INSERT INTO publication_revision
      (id,publication_id,revision_number,document_version_id,source_policy_id,
       source_policy_sha256,review_task_id,snapshot,evaluation,evaluation_sha256,
       action,valid,created_by,created_at)
    VALUES (:revision,:publication,1,:version,:policy,:digest,:review,'{}','{}',:digest,
            'PUBLISH',true,:owner,now())
"""

UPDATE_PUBLICATION_REVISION = """
    UPDATE publication SET current_revision_id=:revision WHERE id=:publication
"""

"""Create the complete MVP core schema.

Revision ID: 20260911_0001
Revises: None
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260911_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _identity_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "imported_emails",
        *_identity_columns(),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(998)),
        sa.Column("sender", sa.String(998)),
        sa.Column("recipients", postgresql.ARRAY(sa.String(998)), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("parse_status", sa.String(32), nullable=False),
        sa.Column("extraction_status", sa.String(32), nullable=False),
        sa.Column("safe_error_summary", sa.String(500)),
        sa.Column("raw_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("char_length(content_sha256) = 64", name="ck_imported_email_sha256"),
        sa.CheckConstraint(
            "parse_status IN ('uploaded','parsing','parsed','parse_failed')",
            name="ck_imported_email_parse_status",
        ),
        sa.CheckConstraint(
            "extraction_status IN ('not_started','extracting','extracted','extraction_failed')",
            name="ck_imported_email_extraction_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_sha256"),
    )
    op.create_table(
        "evidence_segments",
        *_identity_columns(),
        sa.Column("source_item_id", UUID, nullable=False),
        sa.Column("section_type", sa.String(32), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("safe_excerpt", sa.Text()),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("segment_index >= 0", name="ck_evidence_segment_index"),
        sa.CheckConstraint("start_offset >= 0", name="ck_evidence_start_offset"),
        sa.CheckConstraint("end_offset >= start_offset", name="ck_evidence_offset_order"),
        sa.CheckConstraint("char_length(content_sha256) = 64", name="ck_evidence_sha256"),
        sa.CheckConstraint(
            "section_type IN ('subject','sender','recipients','sent_at','current_body','quoted_body')",
            name="ck_evidence_section_type",
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["imported_emails.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_item_id", "segment_index", name="uq_evidence_source_index"),
    )
    op.create_table(
        "test_plans",
        *_identity_columns(),
        sa.Column("source_email_id", UUID, nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_platform_id", sa.String(255)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("current_version >= 1", name="ck_test_plan_current_version"),
        sa.CheckConstraint(
            "status IN ('draft','pending_review','revision_requested','approved','submitting','submitted','submission_failed','unknown')",
            name="ck_test_plan_status",
        ),
        sa.ForeignKeyConstraint(["source_email_id"], ["imported_emails.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_platform_id"),
        sa.UniqueConstraint("source_email_id"),
    )
    op.create_table(
        "test_plan_versions",
        *_identity_columns(),
        sa.Column("test_plan_id", UUID, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("domain_catalog_version", sa.String(64), nullable=False),
        sa.Column("value_catalog_version", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_plan_version_number"),
        sa.CheckConstraint("char_length(content_sha256) = 64", name="ck_plan_version_sha256"),
        sa.CheckConstraint("char_length(prompt_sha256) = 64", name="ck_plan_prompt_sha256"),
        sa.ForeignKeyConstraint(["test_plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("test_plan_id", "version_number", name="uq_plan_version_number"),
        sa.UniqueConstraint("test_plan_id", "content_sha256", name="uq_plan_content_sha256"),
    )
    op.create_table(
        "validation_runs",
        *_identity_columns(),
        sa.Column("test_plan_id", UUID, nullable=False),
        sa.Column("test_plan_version_id", UUID, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("rule_set_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("blocking_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('running','passed','failed')", name="ck_validation_status"),
        sa.CheckConstraint("blocking_count >= 0", name="ck_validation_blocking_count"),
        sa.CheckConstraint("warning_count >= 0", name="ck_validation_warning_count"),
        sa.ForeignKeyConstraint(["test_plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["test_plan_version_id"], ["test_plan_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "validation_issues",
        *_identity_columns(),
        sa.Column("validation_run_id", UUID, nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("field_path", sa.String(512)),
        sa.Column("message", sa.String(500), nullable=False),
        sa.CheckConstraint("severity IN ('blocking','warning')", name="ck_issue_severity"),
        sa.ForeignKeyConstraint(["validation_run_id"], ["validation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_issue_run", "validation_issues", ["validation_run_id"])
    op.create_table(
        "review_records",
        *_identity_columns(),
        sa.Column("test_plan_id", UUID, nullable=False),
        sa.Column("test_plan_version_id", UUID, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("operator_employee_id", sa.String(9), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("comment", sa.String(2000)),
        sa.Column("acknowledged_warning_ids", postgresql.ARRAY(UUID), nullable=False),
        sa.CheckConstraint("operator_employee_id ~ '^[0-9]{9}$'", name="ck_review_employee_id"),
        sa.CheckConstraint(
            "decision IN ('approved','revision_requested')", name="ck_review_decision"
        ),
        sa.CheckConstraint(
            "decision <> 'revision_requested' OR (comment IS NOT NULL AND char_length(trim(comment)) > 0)",
            name="ck_review_revision_comment",
        ),
        sa.ForeignKeyConstraint(["test_plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["test_plan_version_id"], ["test_plan_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "payload_previews",
        *_identity_columns(),
        sa.Column("test_plan_id", UUID, nullable=False),
        sa.Column("test_plan_version_id", UUID, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("mapping_profile_version", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("validation_status", sa.String(24), nullable=False),
        sa.Column("confirmation_token_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "validation_status IN ('valid','invalid')", name="ck_preview_validation_status"
        ),
        sa.CheckConstraint("char_length(payload_sha256) = 64", name="ck_preview_payload_sha256"),
        sa.CheckConstraint(
            "char_length(confirmation_token_sha256) = 64", name="ck_preview_confirmation_sha256"
        ),
        sa.ForeignKeyConstraint(["test_plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["test_plan_version_id"], ["test_plan_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("confirmation_token_sha256"),
    )
    op.create_table(
        "submissions",
        *_identity_columns(),
        sa.Column("test_plan_id", UUID, nullable=False),
        sa.Column("test_plan_version_id", UUID, nullable=False),
        sa.Column("payload_preview_id", UUID, nullable=False),
        sa.Column("mapping_profile_version", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("submission_request_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("operator_name", sa.String(100), nullable=False),
        sa.Column("operator_employee_id", sa.String(9), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_request_id", sa.String(255)),
        sa.Column("external_plan_id", sa.String(255)),
        sa.Column("safe_response_summary", sa.String(500)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("char_length(payload_sha256) = 64", name="ck_submission_payload_sha256"),
        sa.CheckConstraint(
            "char_length(idempotency_key) = 64", name="ck_submission_idempotency_key"
        ),
        sa.CheckConstraint("operator_employee_id ~ '^[0-9]{9}$'", name="ck_submission_employee_id"),
        sa.CheckConstraint(
            "status IN ('submitting','submitted','submission_failed','unknown')",
            name="ck_submission_status",
        ),
        sa.ForeignKeyConstraint(
            ["payload_preview_id"], ["payload_previews.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["test_plan_id"], ["test_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["test_plan_version_id"], ["test_plan_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_plan_id"),
        sa.UniqueConstraint("external_request_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("payload_preview_id"),
        sa.UniqueConstraint("submission_request_id"),
    )
    op.create_table(
        "submission_attempts",
        *_identity_columns(),
        sa.Column("submission_id", UUID, nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("safe_error_summary", sa.String(500)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_number >= 1", name="ck_submission_attempt_number"),
        sa.CheckConstraint(
            "outcome IN ('started','succeeded','rejected','unknown','not_found')",
            name="ck_submission_attempt_outcome",
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "attempt_number", name="uq_submission_attempt_number"),
    )
    op.create_table(
        "audit_events",
        *_identity_columns(),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("actor_name", sa.String(100)),
        sa.Column("actor_employee_id", sa.String(9)),
        sa.Column("request_id", sa.String(128)),
        sa.Column("safe_metadata", JSONB, nullable=False),
        sa.CheckConstraint(
            "actor_employee_id IS NULL OR actor_employee_id ~ '^[0-9]{9}$'",
            name="ck_audit_employee_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_aggregate", "audit_events", ["aggregate_type", "aggregate_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_aggregate", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("submission_attempts")
    op.drop_table("submissions")
    op.drop_table("payload_previews")
    op.drop_table("review_records")
    op.drop_index("ix_validation_issue_run", table_name="validation_issues")
    op.drop_table("validation_issues")
    op.drop_table("validation_runs")
    op.drop_table("test_plan_versions")
    op.drop_table("test_plans")
    op.drop_table("evidence_segments")
    op.drop_table("imported_emails")

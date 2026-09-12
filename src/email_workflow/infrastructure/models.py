from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UuidPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImportedEmail(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "imported_emails"

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(998))
    sender: Mapped[str | None] = mapped_column(String(998))
    recipients: Mapped[list[str]] = mapped_column(ARRAY(String(998)), nullable=False, default=list)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_started"
    )
    safe_error_summary: Mapped[str | None] = mapped_column(String(500))
    raw_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("char_length(content_sha256) = 64", name="ck_imported_email_sha256"),
        CheckConstraint(
            "parse_status IN ('uploaded','parsing','parsed','parse_failed')",
            name="ck_imported_email_parse_status",
        ),
        CheckConstraint(
            "extraction_status IN ('not_started','extracting','extracted','extraction_failed')",
            name="ck_imported_email_extraction_status",
        ),
    )


class EvidenceSegment(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_segments"

    source_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("imported_emails.id", ondelete="CASCADE"), nullable=False
    )
    section_type: Mapped[str] = mapped_column(String(32), nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_excerpt: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("source_item_id", "segment_index", name="uq_evidence_source_index"),
        CheckConstraint("segment_index >= 0", name="ck_evidence_segment_index"),
        CheckConstraint("start_offset >= 0", name="ck_evidence_start_offset"),
        CheckConstraint("end_offset >= start_offset", name="ck_evidence_offset_order"),
        CheckConstraint("char_length(content_sha256) = 64", name="ck_evidence_sha256"),
        CheckConstraint(
            "section_type IN "
            "('subject','sender','recipients','sent_at','current_body','quoted_body')",
            name="ck_evidence_section_type",
        ),
    )


class TestPlan(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "test_plans"

    source_email_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("imported_emails.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    external_platform_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("current_version >= 1", name="ck_test_plan_current_version"),
        CheckConstraint(
            "status IN "
            "('draft','pending_review','revision_requested','approved','submitting',"
            "'submitted','submission_failed','unknown')",
            name="ck_test_plan_status",
        ),
    )


class TestPlanVersion(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "test_plan_versions"

    test_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    value_catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("test_plan_id", "version_number", name="uq_plan_version_number"),
        UniqueConstraint("test_plan_id", "content_sha256", name="uq_plan_content_sha256"),
        CheckConstraint("version_number >= 1", name="ck_plan_version_number"),
        CheckConstraint("char_length(content_sha256) = 64", name="ck_plan_version_sha256"),
        CheckConstraint("char_length(prompt_sha256) = 64", name="ck_plan_prompt_sha256"),
    )


class ValidationRun(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "validation_runs"

    test_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False
    )
    test_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    blocking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('running','passed','failed')", name="ck_validation_status"),
        CheckConstraint("blocking_count >= 0", name="ck_validation_blocking_count"),
        CheckConstraint("warning_count >= 0", name="ck_validation_warning_count"),
    )


class ValidationIssue(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "validation_issues"

    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_runs.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    field_path: Mapped[str | None] = mapped_column(String(512))
    message: Mapped[str] = mapped_column(String(500), nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('blocking','warning')", name="ck_issue_severity"),
        Index("ix_validation_issue_run", "validation_run_id"),
    )


class ReviewRecord(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "review_records"

    test_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False
    )
    test_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_employee_id: Mapped[str] = mapped_column(String(9), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(2000))
    acknowledged_warning_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    __table_args__ = (
        CheckConstraint("operator_employee_id ~ '^[0-9]{9}$'", name="ck_review_employee_id"),
        CheckConstraint("decision IN ('approved','revision_requested')", name="ck_review_decision"),
        CheckConstraint(
            "decision <> 'revision_requested' OR "
            "(comment IS NOT NULL AND char_length(trim(comment)) > 0)",
            name="ck_review_revision_comment",
        ),
    )


class PayloadPreview(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "payload_previews"

    test_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False
    )
    test_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    confirmation_token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "validation_status IN ('valid','invalid')", name="ck_preview_validation_status"
        ),
        CheckConstraint("char_length(payload_sha256) = 64", name="ck_preview_payload_sha256"),
        CheckConstraint(
            "char_length(confirmation_token_sha256) = 64",
            name="ck_preview_confirmation_sha256",
        ),
    )


class Submission(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "submissions"

    test_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False
    )
    test_plan_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    payload_preview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payload_previews.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    mapping_profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    submission_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_employee_id: Mapped[str] = mapped_column(String(9), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_request_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    external_plan_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    safe_response_summary: Mapped[str | None] = mapped_column(String(500))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("char_length(payload_sha256) = 64", name="ck_submission_payload_sha256"),
        CheckConstraint("char_length(idempotency_key) = 64", name="ck_submission_idempotency_key"),
        CheckConstraint("operator_employee_id ~ '^[0-9]{9}$'", name="ck_submission_employee_id"),
        CheckConstraint(
            "status IN ('submitting','submitted','submission_failed','unknown')",
            name="ck_submission_status",
        ),
    )


class SubmissionAttempt(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "submission_attempts"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    safe_error_summary: Mapped[str | None] = mapped_column(String(500))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("submission_id", "attempt_number", name="uq_submission_attempt_number"),
        CheckConstraint("attempt_number >= 1", name="ck_submission_attempt_number"),
        CheckConstraint(
            "outcome IN ('started','succeeded','rejected','unknown','not_found')",
            name="ck_submission_attempt_outcome",
        ),
    )


class AuditEvent(UuidPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_events"

    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(100))
    actor_employee_id: Mapped[str | None] = mapped_column(String(9))
    request_id: Mapped[str | None] = mapped_column(String(128))
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "actor_employee_id IS NULL OR actor_employee_id ~ '^[0-9]{9}$'",
            name="ck_audit_employee_id",
        ),
        Index("ix_audit_aggregate", "aggregate_type", "aggregate_id", "created_at"),
    )

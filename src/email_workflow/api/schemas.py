from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from email_workflow.application.plans import PlanSnapshot
from email_workflow.application.workflow import ValidationResult, VersionResult
from email_workflow.domain.plan import TestPlanContent
from email_workflow.infrastructure.models import (
    EvidenceSegment,
    ImportedEmail,
    ReviewRecord,
    TestPlan,
    TestPlanVersion,
    ValidationIssue,
)


class ImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    subject: str | None
    sender: str | None
    recipients: list[str]
    sent_at: datetime | None
    content_sha256: str
    parse_status: Literal["uploaded", "parsing", "parsed", "parse_failed"]
    extraction_status: Literal["not_started", "extracting", "extracted", "extraction_failed"]
    safe_error_summary: str | None
    created_at: datetime
    raw_expires_at: datetime
    purged_at: datetime | None
    deduplicated: bool = False
    warnings: list[str] = Field(default_factory=list)
    test_plan_id: uuid.UUID | None = None

    @classmethod
    def from_record(
        cls,
        imported: ImportedEmail,
        *,
        deduplicated: bool,
        warnings: list[str] | None = None,
        test_plan_id: uuid.UUID | None = None,
    ) -> ImportResponse:
        return cls.model_validate(
            {
                **{
                    field: getattr(imported, field)
                    for field in cls.model_fields
                    if hasattr(imported, field)
                },
                "deduplicated": deduplicated,
                "warnings": warnings or [],
                "test_plan_id": test_plan_id,
            }
        )


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    source_item_id: uuid.UUID
    section_type: str
    segment_index: int
    start_offset: int
    end_offset: int
    safe_excerpt: str | None
    content_sha256: str
    created_at: datetime
    expires_at: datetime
    purged_at: datetime | None

    @classmethod
    def from_record(cls, segment: EvidenceSegment) -> EvidenceResponse:
        return cls.model_validate({field: getattr(segment, field) for field in cls.model_fields})


class PlanSummaryResponse(BaseModel):
    id: uuid.UUID
    source_email_id: uuid.UUID
    current_version: int
    status: str
    external_platform_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, plan: TestPlan) -> PlanSummaryResponse:
        return cls.model_validate({field: getattr(plan, field) for field in cls.model_fields})


class PlanVersionResponse(BaseModel):
    id: uuid.UUID
    test_plan_id: uuid.UUID
    version_number: int
    content: dict[str, object]
    content_sha256: str
    domain_catalog_version: str
    value_catalog_version: str
    prompt_version: str
    prompt_sha256: str
    created_at: datetime

    @classmethod
    def from_record(cls, version: TestPlanVersion) -> PlanVersionResponse:
        return cls.model_validate({field: getattr(version, field) for field in cls.model_fields})


class PlanResponse(PlanSummaryResponse):
    version: PlanVersionResponse

    @classmethod
    def from_snapshot(cls, snapshot: PlanSnapshot) -> PlanResponse:
        return cls.model_validate(
            {
                **PlanSummaryResponse.from_record(snapshot.plan).model_dump(),
                "version": PlanVersionResponse.from_record(snapshot.version).model_dump(),
            }
        )


class CreateVersionRequest(BaseModel):
    base_version: int = Field(ge=1)
    content: TestPlanContent


class VersionMutationResponse(BaseModel):
    created: bool
    version: PlanVersionResponse

    @classmethod
    def from_result(cls, result: VersionResult) -> VersionMutationResponse:
        return cls(created=result.created, version=PlanVersionResponse.from_record(result.version))


class ValidationIssueResponse(BaseModel):
    id: uuid.UUID
    rule_id: str
    rule_version: str
    severity: Literal["blocking", "warning", "info"]
    field_path: str | None
    message: str
    suggestion: str | None

    @classmethod
    def from_record(cls, issue: ValidationIssue) -> ValidationIssueResponse:
        return cls.model_validate({field: getattr(issue, field) for field in cls.model_fields})


class ValidationResponse(BaseModel):
    id: uuid.UUID
    test_plan_id: uuid.UUID
    test_plan_version_id: uuid.UUID
    content_sha256: str
    rule_set_version: str
    status: Literal["passed", "failed"]
    blocking_count: int
    warning_count: int
    finished_at: datetime
    issues: list[ValidationIssueResponse]

    @classmethod
    def from_result(cls, result: ValidationResult) -> ValidationResponse:
        return cls.model_validate(
            {
                **{
                    field: getattr(result.run, field)
                    for field in cls.model_fields
                    if field != "issues"
                },
                "issues": [ValidationIssueResponse.from_record(issue) for issue in result.issues],
            }
        )


class ReviewRequest(BaseModel):
    decision: Literal["approved", "revision_requested"]
    operator_name: str = Field(min_length=1, max_length=100)
    operator_employee_id: str = Field(pattern=r"^[0-9]{9}$")
    comment: str | None = Field(default=None, max_length=2000)
    validation_run_id: uuid.UUID | None = None
    acknowledged_warning_ids: list[uuid.UUID] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    test_plan_id: uuid.UUID
    test_plan_version_id: uuid.UUID
    content_sha256: str
    operator_name: str
    operator_employee_id: str
    decision: Literal["approved", "revision_requested"]
    comment: str | None
    acknowledged_warning_ids: list[uuid.UUID]
    created_at: datetime

    @classmethod
    def from_record(cls, review: ReviewRecord) -> ReviewResponse:
        return cls.model_validate({field: getattr(review, field) for field in cls.model_fields})

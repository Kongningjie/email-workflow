from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from email_workflow.application.plans import PlanSnapshot
from email_workflow.infrastructure.models import (
    EvidenceSegment,
    ImportedEmail,
    TestPlan,
    TestPlanVersion,
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

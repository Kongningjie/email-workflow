from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Provenance = Literal["source", "user_provided", "derived", "model_suggestion", "unresolved"]
BoundedText = Annotated[str, Field(max_length=20_000)]
EvidenceIdList = Annotated[list[str], Field(max_length=50)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedText(StrictModel):
    value: BoundedText
    evidence_ids: EvidenceIdList


class ExtractedList(StrictModel):
    values: Annotated[list[BoundedText], Field(max_length=100)]
    evidence_ids: EvidenceIdList


class ExtractedRequirement(StrictModel):
    text: BoundedText
    evidence_ids: EvidenceIdList


class ExtractedStep(StrictModel):
    step_number: Annotated[int, Field(ge=1, le=20)]
    action: BoundedText


class ExtractedTestCase(StrictModel):
    title: ExtractedText
    objective: ExtractedText
    preconditions: ExtractedList
    steps: Annotated[list[ExtractedStep], Field(min_length=1, max_length=20)]
    test_data: ExtractedText
    expected_result: ExtractedText
    priority: ExtractedText
    evidence_ids: EvidenceIdList
    provenance: Literal["source", "model_suggestion"]
    open_questions: Annotated[list[BoundedText], Field(max_length=50)]

    @model_validator(mode="after")
    def steps_are_contiguous(self) -> ExtractedTestCase:
        if [step.step_number for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("用例步骤编号必须从 1 开始连续递增")
        return self


class ExtractedDomain(StrictModel):
    domain_key: ExtractedText
    owner_name: ExtractedText
    owner_employee_id: ExtractedText
    execution_start_date: ExtractedText
    execution_end_date: ExtractedText
    scope: ExtractedText
    requirements: Annotated[list[ExtractedRequirement], Field(max_length=100)]
    test_cases: Annotated[list[ExtractedTestCase], Field(max_length=20)]
    evidence_ids: EvidenceIdList
    unresolved_fields: Annotated[list[str], Field(max_length=50)]


class ExtractionPayload(StrictModel):
    plan_name: ExtractedText
    project_name: ExtractedText
    project_code: ExtractedText
    requirement_ids: ExtractedList
    test_type: ExtractedText
    test_stage: ExtractedText
    test_round: ExtractedText
    priority: ExtractedText
    test_version: ExtractedText
    planned_start_date: ExtractedText
    planned_end_date: ExtractedText
    objective: ExtractedText
    scope: ExtractedText
    environment: ExtractedText
    risks: ExtractedList
    dependencies: ExtractedList
    notes: ExtractedText
    open_questions: Annotated[list[BoundedText], Field(max_length=100)]
    details: Annotated[list[ExtractedDomain], Field(max_length=10)]

    @model_validator(mode="after")
    def total_case_limit(self) -> ExtractionPayload:
        if sum(len(detail.test_cases) for detail in self.details) > 100:
            raise ValueError("整个计划最多包含 100 条用例")
        return self


class ExtractionEvidence(StrictModel):
    evidence_id: str
    section_type: str
    text: str


class ExtractionRequest(StrictModel):
    evidence: list[ExtractionEvidence]
    allowed_domains: dict[str, list[str]]
    allowed_test_types: dict[str, list[str]]
    allowed_test_stages: dict[str, list[str]]
    allowed_priorities: dict[str, list[str]]


class EvidenceReference(StrictModel):
    evidence_segment_id: uuid.UUID
    section_type: str
    start_offset: int
    end_offset: int
    content_sha256: str


class FieldMetadata(StrictModel):
    provenance: Provenance
    evidence_references: list[EvidenceReference]


class TestCaseContent(StrictModel):
    title: str
    objective: str
    preconditions: list[str]
    steps: Annotated[list[ExtractedStep], Field(min_length=1, max_length=20)]
    test_data: str
    expected_result: str
    priority: str
    domain_key: str
    evidence_references: list[EvidenceReference]
    provenance: Provenance
    open_questions: list[str]


class RequirementContent(StrictModel):
    text: str
    evidence_references: list[EvidenceReference]
    provenance: Provenance


class TestPlanDetailContent(StrictModel):
    domain_key: str
    domain_name: str
    domain_code: str
    owner_name: str
    owner_employee_id: str
    execution_start_date: date | None
    execution_end_date: date | None
    scope: str
    requirements: Annotated[list[RequirementContent], Field(max_length=100)]
    test_cases: Annotated[list[TestCaseContent], Field(max_length=20)]
    evidence_references: list[EvidenceReference]
    unresolved_fields: list[str]
    field_metadata: dict[str, FieldMetadata]


class TestPlanContent(StrictModel):
    plan_name: str
    project_name: str
    project_code: str
    requirement_ids: list[str]
    test_type: str
    test_stage: str
    test_round: str
    priority: str
    test_version: str
    planned_start_date: date | None
    planned_end_date: date | None
    objective: str
    scope: str
    environment: str
    risks: list[str]
    dependencies: list[str]
    notes: str
    open_questions: list[str]
    evidence_references: list[EvidenceReference]
    details: Annotated[list[TestPlanDetailContent], Field(max_length=10)]
    field_metadata: dict[str, FieldMetadata]

    @model_validator(mode="after")
    def total_case_limit(self) -> TestPlanContent:
        if sum(len(detail.test_cases) for detail in self.details) > 100:
            raise ValueError("整个计划最多包含 100 条用例")
        return self

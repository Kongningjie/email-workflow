from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PlatformStep(PlatformModel):
    step_number: int = Field(alias="stepNumber", ge=1)
    action: str


class PlatformTestCase(PlatformModel):
    title: str
    objective: str
    preconditions: list[str]
    steps: list[PlatformStep]
    test_data: str = Field(alias="testData")
    expected_result: str = Field(alias="expectedResult")
    priority: str


class PlatformDomain(PlatformModel):
    domain_code: str = Field(alias="domainCode")
    owner_name: str = Field(alias="ownerName")
    owner_employee_id: str = Field(alias="ownerEmployeeId", pattern=r"^[0-9]{9}$")
    execution_start_date: date = Field(alias="executionStartDate")
    execution_end_date: date = Field(alias="executionEndDate")
    scope: str
    requirements: list[str]
    test_cases: list[PlatformTestCase] = Field(alias="testCases")


class PlatformPlanPayload(PlatformModel):
    contract_version: str = Field(alias="contractVersion")
    source_system: str = Field(alias="sourceSystem")
    internal_plan_id: uuid.UUID = Field(alias="internalPlanId")
    internal_version: int = Field(alias="internalVersion", ge=1)
    plan_name: str = Field(alias="planName")
    project_name: str = Field(alias="projectName")
    project_code: str = Field(alias="projectCode")
    requirement_ids: list[str] = Field(alias="requirementIds")
    test_type: str = Field(alias="testType")
    test_stage: str = Field(alias="testStage")
    test_round: str = Field(alias="testRound")
    priority: str
    test_version: str = Field(alias="testVersion")
    planned_start_date: date = Field(alias="plannedStartDate")
    planned_end_date: date = Field(alias="plannedEndDate")
    objective: str
    scope: str
    environment: str
    risks: list[str]
    dependencies: list[str]
    domains: list[PlatformDomain]


class GatewayValidationResponse(PlatformModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class GatewaySubmissionReceipt(PlatformModel):
    status: Literal["submitted"]
    external_request_id: str = Field(alias="externalRequestId")
    external_plan_id: str = Field(alias="externalPlanId")
    deduplicated: bool = False


class GatewaySubmissionStatus(PlatformModel):
    status: Literal["submitted", "submission_failed", "not_found"]
    external_request_id: str | None = Field(default=None, alias="externalRequestId")
    external_plan_id: str | None = Field(default=None, alias="externalPlanId")
    safe_summary: str | None = Field(default=None, alias="safeSummary")

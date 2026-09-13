from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from email_workflow.api.schemas import (
    CreateVersionRequest,
    PlanResponse,
    PlanSummaryResponse,
    PlanVersionResponse,
    ReviewRequest,
    ReviewResponse,
    ValidationResponse,
    VersionMutationResponse,
)
from email_workflow.application.plans import PlanQueryService
from email_workflow.application.workflow import PlanWorkflowService, WorkflowError
from email_workflow.core.errors import AppError

router = APIRouter(tags=["test-plans"])


def get_plan_query_service(request: Request) -> PlanQueryService:
    return cast(PlanQueryService, request.app.state.plan_query_service)


def get_plan_workflow_service(request: Request) -> PlanWorkflowService:
    return cast(PlanWorkflowService, request.app.state.plan_workflow_service)


def workflow_error(exc: WorkflowError) -> AppError:
    if exc.code == "test_plan_not_found":
        status_code = 404
    elif exc.code in {
        "base_version_conflict",
        "plan_content_locked",
        "invalid_plan_state",
        "validation_blocked",
        "review_already_decided",
        "stale_validation_run",
    }:
        status_code = 409
    else:
        status_code = 422
    return AppError(code=exc.code, message=exc.message, status_code=status_code)


@router.get("/test-plans", response_model=list[PlanSummaryResponse])
async def list_test_plans(
    service: Annotated[PlanQueryService, Depends(get_plan_query_service)],
) -> list[PlanSummaryResponse]:
    return [PlanSummaryResponse.from_record(plan) for plan in await service.list_plans()]


@router.get("/test-plans/{plan_id}", response_model=PlanResponse)
async def get_test_plan(
    plan_id: uuid.UUID,
    service: Annotated[PlanQueryService, Depends(get_plan_query_service)],
) -> PlanResponse:
    snapshot = await service.get(plan_id)
    if snapshot is None:
        raise AppError(code="test_plan_not_found", message="测试计划不存在", status_code=404)
    return PlanResponse.from_snapshot(snapshot)


@router.get("/test-plans/{plan_id}/versions", response_model=list[PlanVersionResponse])
async def list_test_plan_versions(
    plan_id: uuid.UUID,
    service: Annotated[PlanQueryService, Depends(get_plan_query_service)],
) -> list[PlanVersionResponse]:
    versions = await service.versions(plan_id)
    if versions is None:
        raise AppError(code="test_plan_not_found", message="测试计划不存在", status_code=404)
    return [PlanVersionResponse.from_record(version) for version in versions]


@router.get("/test-plans/{plan_id}/versions/{version_number}", response_model=PlanVersionResponse)
async def get_test_plan_version(
    plan_id: uuid.UUID,
    version_number: int,
    service: Annotated[PlanQueryService, Depends(get_plan_query_service)],
) -> PlanVersionResponse:
    version = await service.version(plan_id, version_number)
    if version is None:
        raise AppError(
            code="test_plan_version_not_found", message="计划版本不存在", status_code=404
        )
    return PlanVersionResponse.from_record(version)


@router.post("/test-plans/{plan_id}/versions", response_model=VersionMutationResponse)
async def create_test_plan_version(
    plan_id: uuid.UUID,
    payload: CreateVersionRequest,
    service: Annotated[PlanWorkflowService, Depends(get_plan_workflow_service)],
) -> VersionMutationResponse:
    try:
        return VersionMutationResponse.from_result(
            await service.create_version(
                plan_id, base_version=payload.base_version, content=payload.content
            )
        )
    except WorkflowError as exc:
        raise workflow_error(exc) from exc


@router.post("/test-plans/{plan_id}/validate", response_model=ValidationResponse)
async def validate_test_plan(
    plan_id: uuid.UUID,
    service: Annotated[PlanWorkflowService, Depends(get_plan_workflow_service)],
) -> ValidationResponse:
    try:
        return ValidationResponse.from_result(await service.validate(plan_id))
    except WorkflowError as exc:
        raise workflow_error(exc) from exc


@router.post("/test-plans/{plan_id}/submit-for-review", response_model=ValidationResponse)
async def submit_test_plan_for_review(
    plan_id: uuid.UUID,
    service: Annotated[PlanWorkflowService, Depends(get_plan_workflow_service)],
) -> ValidationResponse:
    try:
        return ValidationResponse.from_result(await service.submit_for_review(plan_id))
    except WorkflowError as exc:
        raise workflow_error(exc) from exc


@router.post(
    "/test-plans/{plan_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def review_test_plan(
    plan_id: uuid.UUID,
    payload: ReviewRequest,
    service: Annotated[PlanWorkflowService, Depends(get_plan_workflow_service)],
) -> ReviewResponse:
    try:
        review = await service.review(
            plan_id,
            decision=payload.decision,
            operator_name=payload.operator_name,
            operator_employee_id=payload.operator_employee_id,
            comment=payload.comment,
            validation_run_id=payload.validation_run_id,
            acknowledged_warning_ids=payload.acknowledged_warning_ids,
        )
        return ReviewResponse.from_record(review)
    except WorkflowError as exc:
        raise workflow_error(exc) from exc


@router.get("/test-plans/{plan_id}/reviews", response_model=list[ReviewResponse])
async def list_test_plan_reviews(
    plan_id: uuid.UUID,
    service: Annotated[PlanWorkflowService, Depends(get_plan_workflow_service)],
) -> list[ReviewResponse]:
    try:
        return [ReviewResponse.from_record(item) for item in await service.reviews(plan_id)]
    except WorkflowError as exc:
        raise workflow_error(exc) from exc

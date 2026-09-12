from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from email_workflow.api.schemas import PlanResponse, PlanSummaryResponse, PlanVersionResponse
from email_workflow.application.plans import PlanQueryService
from email_workflow.core.errors import AppError

router = APIRouter(tags=["test-plans"])


def get_plan_query_service(request: Request) -> PlanQueryService:
    return cast(PlanQueryService, request.app.state.plan_query_service)


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

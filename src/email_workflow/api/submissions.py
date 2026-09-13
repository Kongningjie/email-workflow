from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from email_workflow.api.schemas import (
    ConfirmSubmissionRequest,
    PayloadPreviewResponse,
    SubmissionResponse,
)
from email_workflow.application.submissions import SubmissionService
from email_workflow.application.workflow import WorkflowError
from email_workflow.core.errors import AppError

router = APIRouter(tags=["submissions"])


def get_submission_service(request: Request) -> SubmissionService:
    return cast(SubmissionService, request.app.state.submission_service)


def submission_error(exc: WorkflowError) -> AppError:
    if exc.code == "platform_unavailable":
        status_code = 503
    elif exc.code in {"test_plan_not_found", "submission_not_found"}:
        status_code = 404
    elif exc.code in {
        "plan_not_approved",
        "approval_mismatch",
        "plan_version_changed",
        "validation_blocked",
        "warnings_changed",
        "payload_changed",
        "invalid_submission_state",
        "retry_not_allowed",
        "confirmation_already_used",
    }:
        status_code = 409
    else:
        status_code = 422
    return AppError(code=exc.code, message=exc.message, status_code=status_code)


@router.post(
    "/test-plans/{plan_id}/payload-previews",
    response_model=PayloadPreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payload_preview(
    plan_id: uuid.UUID,
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> PayloadPreviewResponse:
    try:
        return PayloadPreviewResponse.from_result(await service.create_preview(plan_id))
    except WorkflowError as exc:
        raise submission_error(exc) from exc


@router.post(
    "/test-plans/{plan_id}/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_submission(
    plan_id: uuid.UUID,
    payload: ConfirmSubmissionRequest,
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> SubmissionResponse:
    try:
        return SubmissionResponse.from_record(
            await service.confirm_submission(
                plan_id,
                confirmation_token=payload.confirmation_token,
                payload_sha256=payload.payload_sha256,
                operator_name=payload.operator_name,
                operator_employee_id=payload.operator_employee_id,
            )
        )
    except WorkflowError as exc:
        raise submission_error(exc) from exc


@router.get("/test-plans/{plan_id}/submissions", response_model=list[SubmissionResponse])
async def list_submissions(
    plan_id: uuid.UUID,
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> list[SubmissionResponse]:
    try:
        return [
            SubmissionResponse.from_record(item) for item in await service.list_for_plan(plan_id)
        ]
    except WorkflowError as exc:
        raise submission_error(exc) from exc


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: uuid.UUID,
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> SubmissionResponse:
    submission = await service.get(submission_id)
    if submission is None:
        raise AppError(code="submission_not_found", message="提交记录不存在", status_code=404)
    return SubmissionResponse.from_record(submission)


@router.post("/submissions/{submission_id}/reconcile", response_model=SubmissionResponse)
async def reconcile_submission(
    submission_id: uuid.UUID,
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> SubmissionResponse:
    try:
        return SubmissionResponse.from_record(await service.reconcile(submission_id))
    except WorkflowError as exc:
        raise submission_error(exc) from exc


@router.post("/submissions/{submission_id}/retry", response_model=SubmissionResponse)
async def retry_submission(
    submission_id: uuid.UUID,
    service: Annotated[SubmissionService, Depends(get_submission_service)],
) -> SubmissionResponse:
    try:
        return SubmissionResponse.from_record(await service.retry(submission_id))
    except WorkflowError as exc:
        raise submission_error(exc) from exc

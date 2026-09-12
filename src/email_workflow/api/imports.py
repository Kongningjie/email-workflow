from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from email_workflow.api.schemas import EvidenceResponse, ImportResponse
from email_workflow.application.imports import EmailImportService
from email_workflow.core.config import Settings
from email_workflow.core.errors import AppError
from email_workflow.infrastructure.email_parser import EmailParseError

router = APIRouter(tags=["imports"])


def get_import_service(request: Request) -> EmailImportService:
    return cast(EmailImportService, request.app.state.import_service)


def get_settings_from_app(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


@router.post("/imports", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def create_import(
    response: Response,
    file: Annotated[UploadFile, File(description="单个 .eml 邮件文件")],
    confirm_external_processing: Annotated[
        bool,
        Form(description="确认清洗后的邮件内容将发送至 DashScope"),
    ],
    service: Annotated[EmailImportService, Depends(get_import_service)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> ImportResponse:
    raw = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    try:
        result = await service.import_email(
            filename=file.filename,
            content_type=file.content_type,
            raw=raw,
            external_processing_confirmed=confirm_external_processing,
        )
    except EmailParseError as exc:
        raise AppError(code=exc.code, message=str(exc), status_code=422, field="file") from exc
    if result.deduplicated:
        response.status_code = status.HTTP_200_OK
    return ImportResponse.from_record(
        result.imported_email,
        deduplicated=result.deduplicated,
        warnings=[warning.value for warning in result.warnings],
        test_plan_id=result.test_plan_id,
    )


@router.get("/imports/{import_id}", response_model=ImportResponse)
async def get_import(
    import_id: uuid.UUID,
    service: Annotated[EmailImportService, Depends(get_import_service)],
) -> ImportResponse:
    imported = await service.get_import(import_id)
    if imported is None:
        raise AppError(code="import_not_found", message="导入记录不存在", status_code=404)
    return ImportResponse.from_record(
        imported,
        deduplicated=False,
        test_plan_id=await service.get_plan_id(imported.id),
    )


@router.get("/evidence/{segment_id}", response_model=EvidenceResponse)
async def get_evidence(
    segment_id: uuid.UUID,
    service: Annotated[EmailImportService, Depends(get_import_service)],
) -> EvidenceResponse:
    segment = await service.get_evidence(segment_id)
    if segment is None:
        raise AppError(code="evidence_not_found", message="证据片段不存在", status_code=404)
    return EvidenceResponse.from_record(segment)

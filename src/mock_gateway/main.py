from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ValidationError

from email_workflow.core.catalogs import load_mapping_document
from email_workflow.core.logging import configure_logging
from email_workflow.core.signing import verify_signature
from email_workflow.domain.platform import (
    GatewaySubmissionReceipt,
    GatewaySubmissionStatus,
    GatewayValidationResponse,
    PlatformPlanPayload,
)

configure_logging("INFO")
app = FastAPI(title="Mock 测试管理平台", version="0.1.0")
_mapping = load_mapping_document(
    Path(os.getenv("CONFIG_DIR", "config")) / "mappings/mock-platform-v1.yaml"
)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@dataclass(slots=True)
class StoredSubmission:
    idempotency_key: str
    submission_request_id: uuid.UUID
    payload_sha256: str
    status: str
    external_request_id: str | None
    external_plan_id: str | None


_by_idempotency_key: dict[str, StoredSubmission] = {}
_by_request_id: dict[uuid.UUID, StoredSubmission] = {}
_state_lock = asyncio.Lock()


def reset_mock_state() -> None:
    _by_idempotency_key.clear()
    _by_request_id.clear()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="mock-gateway")


@app.post("/mock/v1/test-plans/validate", response_model=GatewayValidationResponse)
async def validate_payload(request: Request) -> GatewayValidationResponse:
    if request.headers.get("X-Mock-Scenario") == "validation_failed":
        raise HTTPException(status_code=422, detail="模拟平台校验失败")
    try:
        payload = PlatformPlanPayload.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="平台报文格式错误") from exc
    errors = _payload_errors(payload)
    return GatewayValidationResponse(valid=not errors, errors=errors)


@app.post("/mock/v1/test-plans", response_model=GatewaySubmissionReceipt)
async def submit_plan(request: Request) -> GatewaySubmissionReceipt:
    body = await request.body()
    idempotency_key, submission_request_id, payload_sha256 = _verify_request(request, body=body)
    scenario = request.headers.get("X-Mock-Scenario", "success")
    if scenario == "timeout":
        await asyncio.sleep(10)
    if scenario == "reject":
        raise HTTPException(status_code=422, detail="模拟业务字段拒绝")
    if scenario == "server_error":
        raise HTTPException(status_code=503, detail="模拟平台服务异常")
    try:
        payload = PlatformPlanPayload.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="平台报文格式错误") from exc
    if _payload_errors(payload):
        raise HTTPException(status_code=422, detail="平台报文校验失败")

    async with _state_lock:
        existing = _by_idempotency_key.get(idempotency_key)
        if existing is not None:
            if (
                existing.submission_request_id != submission_request_id
                or existing.payload_sha256 != payload_sha256
            ):
                raise HTTPException(status_code=409, detail="幂等键参数不一致")
            if existing.status != "submitted":
                raise HTTPException(status_code=409, detail="首次请求未成功")
            return _receipt(existing, deduplicated=True)

        if scenario == "unknown_not_found":
            raise HTTPException(status_code=503, detail="模拟响应丢失且未创建")
        status = "submission_failed" if scenario == "unknown_then_failed" else "submitted"
        record = StoredSubmission(
            idempotency_key=idempotency_key,
            submission_request_id=submission_request_id,
            payload_sha256=payload_sha256,
            status=status,
            external_request_id=f"REQ-{submission_request_id.hex[:12]}",
            external_plan_id=(
                f"PLAN-{submission_request_id.hex[:12]}" if status == "submitted" else None
            ),
        )
        _by_idempotency_key[idempotency_key] = record
        _by_request_id[submission_request_id] = record
        if scenario in {"unknown_then_success", "unknown_then_failed"}:
            raise HTTPException(status_code=503, detail="模拟平台响应丢失")
        return _receipt(record, deduplicated=False)


@app.get("/mock/v1/submissions/{submission_request_id}", response_model=GatewaySubmissionStatus)
async def submission_status(
    submission_request_id: uuid.UUID, request: Request
) -> GatewaySubmissionStatus:
    idempotency_key, header_request_id, _ = _verify_request(request, body=b"")
    if header_request_id != submission_request_id:
        raise HTTPException(status_code=400, detail="请求 ID 不一致")
    record = _by_request_id.get(submission_request_id)
    if record is None or record.idempotency_key != idempotency_key:
        raise HTTPException(status_code=404, detail="未找到提交请求")
    return GatewaySubmissionStatus(
        status=record.status,
        external_request_id=record.external_request_id,
        external_plan_id=record.external_plan_id,
        safe_summary="模拟平台已确认结果",
    )


def _verify_request(request: Request, *, body: bytes) -> tuple[str, uuid.UUID, str]:
    headers = request.headers
    required = (
        "X-Key-Id",
        "X-Timestamp",
        "X-Content-SHA256",
        "X-Signature",
        "Idempotency-Key",
        "X-Submission-Request-Id",
    )
    if any(not headers.get(name) for name in required):
        raise HTTPException(status_code=401, detail="签名请求头不完整")
    expected_key_id = os.getenv("MOCK_GATEWAY_KEY_ID", "local-demo")
    secret = os.getenv("MOCK_GATEWAY_HMAC_SECRET", "replace-with-a-local-demo-secret")
    if headers["X-Key-Id"] != expected_key_id:
        raise HTTPException(status_code=401, detail="未知签名密钥")
    try:
        timestamp_value = int(headers["X-Timestamp"])
        submission_request_id = uuid.UUID(headers["X-Submission-Request-Id"])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="签名请求头格式错误") from exc
    if abs(int(time.time()) - timestamp_value) > 300:
        raise HTTPException(status_code=401, detail="签名已过期")
    content_sha256 = hashlib.sha256(body).hexdigest()
    if content_sha256 != headers["X-Content-SHA256"]:
        raise HTTPException(status_code=401, detail="正文哈希不一致")
    fields = {
        "method": request.method,
        "path": request.url.path,
        "timestamp": headers["X-Timestamp"],
        "idempotency_key": headers["Idempotency-Key"],
        "submission_request_id": str(submission_request_id),
        "content_sha256": content_sha256,
    }
    if not verify_signature(signature=headers["X-Signature"], secret=secret, **fields):
        raise HTTPException(status_code=401, detail="签名无效")
    return headers["Idempotency-Key"], submission_request_id, content_sha256


def _payload_errors(payload: PlatformPlanPayload) -> list[str]:
    errors: list[str] = []
    if not payload.plan_name.strip():
        errors.append("planName 必填")
    if not payload.domains:
        errors.append("domains 至少一项")
    if any(not domain.test_cases for domain in payload.domains):
        errors.append("每个领域至少需要一条用例")
    if len(payload.domains) > _mapping.limits["max_domains"]:
        errors.append("domains 超过条目上限")
    if sum(len(domain.test_cases) for domain in payload.domains) > _mapping.limits[
        "max_cases_total"
    ]:
        errors.append("testCases 超过总条目上限")
    fields = (
        ("planName", payload.plan_name, "plan_name"),
        ("projectName", payload.project_name, "project_name"),
        ("projectCode", payload.project_code, "project_code"),
        ("testRound", payload.test_round, "test_round"),
        ("testVersion", payload.test_version, "test_version"),
        ("objective", payload.objective, "objective"),
        ("scope", payload.scope, "scope"),
        ("environment", payload.environment, "environment"),
    )
    errors.extend(
        f"{field} 超过长度上限"
        for field, value, limit_name in fields
        if len(value) > _mapping.limits[limit_name]
    )
    for domain_index, domain in enumerate(payload.domains):
        if len(domain.test_cases) > _mapping.limits["max_cases_per_domain"]:
            errors.append(f"domains[{domain_index}].testCases 超过条目上限")
        if len(domain.scope) > _mapping.limits["domain_scope"]:
            errors.append(f"domains[{domain_index}].scope 超过长度上限")
        if any(len(item) > _mapping.limits["requirement"] for item in domain.requirements):
            errors.append(f"domains[{domain_index}].requirements 超过长度上限")
        for case_index, case in enumerate(domain.test_cases):
            prefix = f"domains[{domain_index}].testCases[{case_index}]"
            if len(case.steps) > _mapping.limits["max_steps_per_case"]:
                errors.append(f"{prefix}.steps 超过条目上限")
            if len(case.title) > _mapping.limits["case_title"]:
                errors.append(f"{prefix}.title 超过长度上限")
            if len(case.objective) > _mapping.limits["case_objective"]:
                errors.append(f"{prefix}.objective 超过长度上限")
            if len(case.expected_result) > _mapping.limits["case_expected_result"]:
                errors.append(f"{prefix}.expectedResult 超过长度上限")
            if any(len(step.action) > _mapping.limits["case_step"] for step in case.steps):
                errors.append(f"{prefix}.steps 超过长度上限")
    return errors


def _receipt(record: StoredSubmission, *, deduplicated: bool) -> GatewaySubmissionReceipt:
    if record.external_request_id is None or record.external_plan_id is None:
        raise HTTPException(status_code=409, detail="提交尚未成功")
    return GatewaySubmissionReceipt(
        status="submitted",
        external_request_id=record.external_request_id,
        external_plan_id=record.external_plan_id,
        deduplicated=deduplicated,
    )

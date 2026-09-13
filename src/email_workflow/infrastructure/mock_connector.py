from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable

import httpx

from email_workflow.application.connector import ConnectorIndeterminate, ConnectorRejected
from email_workflow.core.canonical import canonical_bytes
from email_workflow.core.signing import sign_request
from email_workflow.domain.platform import (
    GatewaySubmissionReceipt,
    GatewaySubmissionStatus,
    GatewayValidationResponse,
    PlatformPlanPayload,
)


class MockTestManagementConnector:
    def __init__(
        self,
        *,
        base_url: str,
        key_id: str,
        hmac_secret: str,
        timeout_seconds: float = 5,
        clock: Callable[[], float] = time.time,
        scenario: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.key_id = key_id
        self.hmac_secret = hmac_secret
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self.scenario = scenario
        self.transport = transport

    async def validate_payload(self, payload: PlatformPlanPayload) -> GatewayValidationResponse:
        path = "/mock/v1/test-plans/validate"
        try:
            async with self._client() as client:
                response = await client.post(
                    path,
                    content=canonical_bytes(payload.model_dump(mode="json", by_alias=True)),
                    headers={"Content-Type": "application/json", **self._scenario_header()},
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ConnectorIndeterminate("平台校验连接失败") from exc
        if response.status_code >= 500:
            raise ConnectorIndeterminate("平台校验暂时不可用")
        if response.status_code >= 400:
            return GatewayValidationResponse(valid=False, errors=["平台报文校验失败"])
        return GatewayValidationResponse.model_validate(response.json())

    async def submit_plan(
        self,
        payload: PlatformPlanPayload,
        *,
        idempotency_key: str,
        submission_request_id: uuid.UUID,
    ) -> GatewaySubmissionReceipt:
        path = "/mock/v1/test-plans"
        body = canonical_bytes(payload.model_dump(mode="json", by_alias=True))
        headers = self._signed_headers(
            method="POST",
            path=path,
            body_sha256=hashlib.sha256(body).hexdigest(),
            idempotency_key=idempotency_key,
            submission_request_id=submission_request_id,
        )
        headers.update(self._scenario_header())
        try:
            async with self._client() as client:
                response = await client.post(path, content=body, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ConnectorIndeterminate("平台提交结果未知") from exc
        if response.status_code >= 500:
            raise ConnectorIndeterminate("平台提交结果未知")
        if response.status_code >= 400:
            raise ConnectorRejected(response.status_code, "平台明确拒绝提交")
        return GatewaySubmissionReceipt.model_validate(response.json())

    async def get_submission_status(
        self,
        submission_request_id: uuid.UUID,
        *,
        idempotency_key: str,
    ) -> GatewaySubmissionStatus:
        path = f"/mock/v1/submissions/{submission_request_id}"
        headers = self._signed_headers(
            method="GET",
            path=path,
            body_sha256=hashlib.sha256(b"").hexdigest(),
            idempotency_key=idempotency_key,
            submission_request_id=submission_request_id,
        )
        try:
            async with self._client() as client:
                response = await client.get(path, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ConnectorIndeterminate("平台对账连接失败") from exc
        if response.status_code >= 500:
            raise ConnectorIndeterminate("平台对账暂时不可用")
        if response.status_code == 404:
            return GatewaySubmissionStatus(status="not_found", safe_summary="平台未找到请求")
        if response.status_code >= 400:
            raise ConnectorRejected(response.status_code, "平台明确拒绝对账")
        return GatewaySubmissionStatus.model_validate(response.json())

    def _signed_headers(
        self,
        *,
        method: str,
        path: str,
        body_sha256: str,
        idempotency_key: str,
        submission_request_id: uuid.UUID,
    ) -> dict[str, str]:
        timestamp = str(int(self.clock()))
        fields = {
            "method": method,
            "path": path,
            "timestamp": timestamp,
            "idempotency_key": idempotency_key,
            "submission_request_id": str(submission_request_id),
            "content_sha256": body_sha256,
        }
        return {
            "Content-Type": "application/json",
            "X-Key-Id": self.key_id,
            "X-Timestamp": timestamp,
            "X-Content-SHA256": body_sha256,
            "X-Signature": sign_request(secret=self.hmac_secret, **fields),
            "Idempotency-Key": idempotency_key,
            "X-Submission-Request-Id": str(submission_request_id),
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
        )

    def _scenario_header(self) -> dict[str, str]:
        return {"X-Mock-Scenario": self.scenario} if self.scenario else {}

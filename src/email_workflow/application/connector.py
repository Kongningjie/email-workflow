from __future__ import annotations

import uuid
from typing import Protocol

from email_workflow.domain.platform import (
    GatewaySubmissionReceipt,
    GatewaySubmissionStatus,
    GatewayValidationResponse,
    PlatformPlanPayload,
)


class ConnectorRejected(Exception):
    def __init__(self, status_code: int, safe_summary: str) -> None:
        super().__init__(safe_summary)
        self.status_code = status_code
        self.safe_summary = safe_summary


class ConnectorIndeterminate(Exception):
    def __init__(self, safe_summary: str) -> None:
        super().__init__(safe_summary)
        self.safe_summary = safe_summary


class TestManagementConnector(Protocol):
    async def validate_payload(self, payload: PlatformPlanPayload) -> GatewayValidationResponse: ...

    async def submit_plan(
        self,
        payload: PlatformPlanPayload,
        *,
        idempotency_key: str,
        submission_request_id: uuid.UUID,
    ) -> GatewaySubmissionReceipt: ...

    async def get_submission_status(
        self,
        submission_request_id: uuid.UUID,
        *,
        idempotency_key: str,
    ) -> GatewaySubmissionStatus: ...

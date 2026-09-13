from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_workflow.application.connector import (
    ConnectorIndeterminate,
    ConnectorRejected,
    TestManagementConnector,
)
from email_workflow.application.mapping import (
    PayloadMappingError,
    PlatformPayloadMapper,
    submission_idempotency_key,
)
from email_workflow.application.workflow import PlanWorkflowService, ValidationResult, WorkflowError
from email_workflow.core.canonical import canonical_bytes, canonical_sha256
from email_workflow.domain.plan import TestPlanContent
from email_workflow.domain.platform import GatewaySubmissionStatus, PlatformPlanPayload
from email_workflow.infrastructure.models import (
    PayloadPreview,
    ReviewRecord,
    Submission,
    SubmissionAttempt,
    TestPlan,
    TestPlanVersion,
    ValidationIssue,
)


@dataclass(frozen=True, slots=True)
class PreviewResult:
    preview: PayloadPreview
    confirmation_token: str
    canonical_json: str


class SubmissionService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        workflow_service: PlanWorkflowService,
        mapper: PlatformPayloadMapper,
        connector: TestManagementConnector,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.workflow_service = workflow_service
        self.mapper = mapper
        self.connector = connector
        self.clock = clock or (lambda: datetime.now(UTC))
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    async def create_preview(self, plan_id: uuid.UUID) -> PreviewResult:
        validation = await self.workflow_service.validate(plan_id)
        if validation.run.blocking_count:
            raise WorkflowError("validation_blocked", "存在阻断问题，不能生成报文预览")  # noqa: RUF001
        async with self.session_factory() as session:
            plan, version, review = await self._approved_snapshot(session, plan_id)
            if validation.run.test_plan_version_id != version.id:
                raise WorkflowError("plan_version_changed", "计划版本已变化，请重试")  # noqa: RUF001
            await self._verify_warning_signatures(session, validation, review)
            try:
                payload = self.mapper.map(
                    plan_id=plan.id,
                    version_number=version.version_number,
                    content=TestPlanContent.model_validate(version.content),
                )
            except PayloadMappingError as exc:
                raise WorkflowError("payload_mapping_failed", str(exc)) from exc
        try:
            gateway_validation = await self.connector.validate_payload(payload)
        except ConnectorIndeterminate as exc:
            raise WorkflowError("platform_unavailable", "Mock 平台校验暂时不可用") from exc
        if not gateway_validation.valid:
            raise WorkflowError("platform_validation_failed", "Mock 平台报文校验未通过")
        payload_dict = payload.model_dump(mode="json", by_alias=True)
        payload_sha256 = canonical_sha256(payload_dict)
        token = self.token_factory()
        token_sha256 = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = self.clock()
        async with self.session_factory() as session, session.begin():
            plan = await self._locked_plan(session, plan_id)
            if plan.status != "approved" or plan.current_version != version.version_number:
                raise WorkflowError("plan_version_changed", "批准状态或计划版本已变化")
            current = await self._version(session, plan.id, plan.current_version)
            if current.id != version.id or current.content_sha256 != version.content_sha256:
                raise WorkflowError("plan_version_changed", "批准版本内容已变化")
            preview = PayloadPreview(
                id=uuid.uuid4(),
                test_plan_id=plan.id,
                test_plan_version_id=version.id,
                content_sha256=version.content_sha256,
                mapping_profile_version=self.mapper.mapping.version,
                payload=payload_dict,
                payload_sha256=payload_sha256,
                validation_status="valid",
                confirmation_token_sha256=token_sha256,
                expires_at=now + timedelta(minutes=15),
            )
            session.add(preview)
            await session.flush()
            return PreviewResult(
                preview=preview,
                confirmation_token=token,
                canonical_json=canonical_bytes(payload_dict).decode("utf-8"),
            )

    async def confirm_submission(
        self,
        plan_id: uuid.UUID,
        *,
        confirmation_token: str,
        payload_sha256: str,
        operator_name: str,
        operator_employee_id: str,
    ) -> Submission:
        self._validate_operator(operator_name, operator_employee_id)
        token_sha256 = hashlib.sha256(confirmation_token.encode("utf-8")).hexdigest()
        async with self.session_factory() as session:
            preview = await session.scalar(
                select(PayloadPreview).where(
                    PayloadPreview.test_plan_id == plan_id,
                    PayloadPreview.confirmation_token_sha256 == token_sha256,
                )
            )
            if preview is None:
                raise WorkflowError("invalid_confirmation_token", "确认令牌无效")
            existing = await session.scalar(
                select(Submission).where(Submission.payload_preview_id == preview.id)
            )
            if existing is not None:
                self._verify_repeated_confirmation(
                    existing, payload_sha256, operator_name, operator_employee_id
                )
                return existing
            if preview.expires_at <= self.clock() or preview.payload_sha256 != payload_sha256:
                raise WorkflowError("invalid_confirmation", "确认令牌已过期或报文哈希不一致")
            preview_payload = PlatformPlanPayload.model_validate(preview.payload)
            idempotency_key = submission_idempotency_key(
                plan_id=plan_id,
                version_number=preview_payload.internal_version,
                payload=preview_payload,
            )
            same_target = await session.scalar(
                select(Submission).where(Submission.idempotency_key == idempotency_key)
            )
            if same_target is not None:
                self._verify_repeated_confirmation(
                    same_target, payload_sha256, operator_name, operator_employee_id
                )
                return same_target

        validation = await self.workflow_service.validate(plan_id)
        if validation.run.blocking_count:
            raise WorkflowError("validation_blocked", "提交前校验发现阻断问题")
        async with self.session_factory() as session:
            plan, version, review = await self._approved_snapshot(session, plan_id)
            if version.id != preview.test_plan_version_id:
                raise WorkflowError("plan_version_changed", "确认令牌不属于当前批准版本")
            await self._verify_warning_signatures(session, validation, review)
            payload = self.mapper.map(
                plan_id=plan.id,
                version_number=version.version_number,
                content=TestPlanContent.model_validate(version.content),
            )
            rebuilt = payload.model_dump(mode="json", by_alias=True)
            rebuilt_sha256 = canonical_sha256(rebuilt)
            if rebuilt_sha256 != preview.payload_sha256 or rebuilt != preview.payload:
                raise WorkflowError("payload_changed", "服务端重建报文与预览不一致")
        try:
            gateway_validation = await self.connector.validate_payload(payload)
        except ConnectorIndeterminate as exc:
            raise WorkflowError("platform_unavailable", "提交前平台校验暂时不可用") from exc
        if not gateway_validation.valid:
            raise WorkflowError("platform_validation_failed", "提交前平台校验未通过")

        submission_request_id = uuid.uuid4()
        async with self.session_factory() as session, session.begin():
            plan = await self._locked_plan(session, plan_id)
            existing = await session.scalar(
                select(Submission).where(
                    or_(
                        Submission.payload_preview_id == preview.id,
                        Submission.idempotency_key == idempotency_key,
                    )
                )
            )
            if existing is not None:
                self._verify_repeated_confirmation(
                    existing, payload_sha256, operator_name, operator_employee_id
                )
                return existing  # type: ignore[no-any-return]
            if plan.status != "approved" or plan.current_version != version.version_number:
                raise WorkflowError("plan_version_changed", "批准状态或计划版本已变化")
            submission = Submission(
                id=uuid.uuid4(),
                test_plan_id=plan.id,
                test_plan_version_id=version.id,
                payload_preview_id=preview.id,
                mapping_profile_version=self.mapper.mapping.version,
                payload_sha256=preview.payload_sha256,
                submission_request_id=submission_request_id,
                idempotency_key=idempotency_key,
                status="submitting",
                operator_name=operator_name.strip(),
                operator_employee_id=operator_employee_id,
                confirmed_at=self.clock(),
                external_request_id=None,
                external_plan_id=None,
                safe_response_summary=None,
                finished_at=None,
            )
            session.add(submission)
            await session.flush()
            session.add(
                SubmissionAttempt(
                    id=uuid.uuid4(),
                    submission_id=submission.id,
                    attempt_number=1,
                    request_id=str(submission_request_id),
                    outcome="started",
                    http_status=None,
                    safe_error_summary=None,
                    finished_at=None,
                )
            )
            plan.status = "submitting"
        return await self._send(submission.id, payload)

    async def reconcile(self, submission_id: uuid.UUID) -> Submission:
        async with self.session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise WorkflowError("submission_not_found", "提交记录不存在")
            if submission.status != "unknown":
                raise WorkflowError("invalid_submission_state", "只有未知状态可以对账")
        try:
            status = await self.connector.get_submission_status(
                submission.submission_request_id,
                idempotency_key=submission.idempotency_key,
            )
        except ConnectorIndeterminate:
            status = GatewaySubmissionStatus(status="not_found", safe_summary="对账结果仍未知")
            outcome = "unknown"
        except ConnectorRejected as exc:
            raise WorkflowError("platform_reconcile_rejected", exc.safe_summary) from exc
        else:
            outcome = {
                "submitted": "succeeded",
                "submission_failed": "rejected",
                "not_found": "not_found",
            }[status.status]
        return await self._apply_reconciliation(submission_id, status, outcome)

    async def retry(self, submission_id: uuid.UUID) -> Submission:
        async with self.session_factory() as session, session.begin():
            submission = await session.scalar(
                select(Submission).where(Submission.id == submission_id).with_for_update()
            )
            if submission is None:
                raise WorkflowError("submission_not_found", "提交记录不存在")
            latest = await session.scalar(
                select(SubmissionAttempt)
                .where(SubmissionAttempt.submission_id == submission.id)
                .order_by(SubmissionAttempt.attempt_number.desc())
                .limit(1)
            )
            if submission.status != "unknown" or latest is None or latest.outcome != "not_found":
                raise WorkflowError("retry_not_allowed", "仅在平台明确 not_found 后允许重试")
            preview = await session.get(PayloadPreview, submission.payload_preview_id)
            if preview is None:
                raise RuntimeError("提交预览不存在")
            payload = PlatformPlanPayload.model_validate(preview.payload)
            next_attempt = latest.attempt_number + 1
            session.add(
                SubmissionAttempt(
                    id=uuid.uuid4(),
                    submission_id=submission.id,
                    attempt_number=next_attempt,
                    request_id=str(submission.submission_request_id),
                    outcome="started",
                    http_status=None,
                    safe_error_summary=None,
                    finished_at=None,
                )
            )
            submission.status = "submitting"
            plan = await self._locked_plan(session, submission.test_plan_id)
            plan.status = "submitting"
        return await self._send(submission_id, payload)

    async def get(self, submission_id: uuid.UUID) -> Submission | None:
        async with self.session_factory() as session:
            return await session.get(Submission, submission_id)

    async def list_for_plan(self, plan_id: uuid.UUID) -> list[Submission]:
        async with self.session_factory() as session:
            if await session.get(TestPlan, plan_id) is None:
                raise WorkflowError("test_plan_not_found", "测试计划不存在")
            statement = (
                select(Submission)
                .where(Submission.test_plan_id == plan_id)
                .order_by(Submission.created_at.desc(), Submission.id)
            )
            return list((await session.scalars(statement)).all())

    async def _send(self, submission_id: uuid.UUID, payload: PlatformPlanPayload) -> Submission:
        async with self.session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise RuntimeError("提交记录不存在")
        try:
            receipt = await self.connector.submit_plan(
                payload,
                idempotency_key=submission.idempotency_key,
                submission_request_id=submission.submission_request_id,
            )
        except ConnectorRejected as exc:
            return await self._finish_attempt(
                submission_id,
                status="submission_failed",
                outcome="rejected",
                http_status=exc.status_code,
                safe_summary=exc.safe_summary,
            )
        except ConnectorIndeterminate as exc:
            return await self._finish_attempt(
                submission_id,
                status="unknown",
                outcome="unknown",
                http_status=None,
                safe_summary=exc.safe_summary,
            )
        return await self._finish_attempt(
            submission_id,
            status="submitted",
            outcome="succeeded",
            http_status=200,
            safe_summary="平台提交成功",
            external_request_id=receipt.external_request_id,
            external_plan_id=receipt.external_plan_id,
        )

    async def _finish_attempt(
        self,
        submission_id: uuid.UUID,
        *,
        status: str,
        outcome: str,
        http_status: int | None,
        safe_summary: str,
        external_request_id: str | None = None,
        external_plan_id: str | None = None,
    ) -> Submission:
        async with self.session_factory() as session, session.begin():
            submission = await session.scalar(
                select(Submission).where(Submission.id == submission_id).with_for_update()
            )
            if submission is None:
                raise RuntimeError("提交记录不存在")
            attempt = await session.scalar(
                select(SubmissionAttempt)
                .where(SubmissionAttempt.submission_id == submission.id)
                .order_by(SubmissionAttempt.attempt_number.desc())
                .limit(1)
            )
            if attempt is None:
                raise RuntimeError("提交尝试不存在")
            now = self.clock()
            attempt.outcome = outcome
            attempt.http_status = http_status
            attempt.safe_error_summary = None if outcome == "succeeded" else safe_summary
            attempt.finished_at = now
            submission.status = status
            submission.safe_response_summary = safe_summary
            submission.external_request_id = external_request_id
            submission.external_plan_id = external_plan_id
            submission.finished_at = now if status in {"submitted", "submission_failed"} else None
            plan = await self._locked_plan(session, submission.test_plan_id)
            plan.status = status
            if status == "submitted":
                plan.external_platform_id = external_plan_id
            return submission

    async def _apply_reconciliation(
        self,
        submission_id: uuid.UUID,
        gateway_status: GatewaySubmissionStatus,
        outcome: str,
    ) -> Submission:
        async with self.session_factory() as session, session.begin():
            submission = await session.scalar(
                select(Submission).where(Submission.id == submission_id).with_for_update()
            )
            if submission is None or submission.status != "unknown":
                raise WorkflowError("invalid_submission_state", "提交状态已变化")
            latest_number = await session.scalar(
                select(func.max(SubmissionAttempt.attempt_number)).where(
                    SubmissionAttempt.submission_id == submission.id
                )
            )
            session.add(
                SubmissionAttempt(
                    id=uuid.uuid4(),
                    submission_id=submission.id,
                    attempt_number=(latest_number or 0) + 1,
                    request_id=str(submission.submission_request_id),
                    outcome=outcome,
                    http_status=200 if outcome != "unknown" else None,
                    safe_error_summary=gateway_status.safe_summary,
                    finished_at=self.clock(),
                )
            )
            if gateway_status.status == "submitted":
                submission.status = "submitted"
                submission.external_request_id = gateway_status.external_request_id
                submission.external_plan_id = gateway_status.external_plan_id
                submission.finished_at = self.clock()
            elif gateway_status.status == "submission_failed":
                submission.status = "submission_failed"
                submission.finished_at = self.clock()
            submission.safe_response_summary = gateway_status.safe_summary
            plan = await self._locked_plan(session, submission.test_plan_id)
            plan.status = submission.status
            if submission.status == "submitted":
                plan.external_platform_id = submission.external_plan_id
            return submission

    async def _approved_snapshot(
        self, session: AsyncSession, plan_id: uuid.UUID
    ) -> tuple[TestPlan, TestPlanVersion, ReviewRecord]:
        plan = await session.get(TestPlan, plan_id)
        if plan is None:
            raise WorkflowError("test_plan_not_found", "测试计划不存在")
        if plan.status != "approved":
            raise WorkflowError("plan_not_approved", "只有已批准计划可以执行该操作")
        version = await self._version(session, plan.id, plan.current_version)
        review = await session.scalar(
            select(ReviewRecord).where(ReviewRecord.test_plan_version_id == version.id)
        )
        if (
            review is None
            or review.decision != "approved"
            or review.content_sha256 != version.content_sha256
        ):
            raise WorkflowError("approval_mismatch", "当前版本没有有效批准记录")
        return plan, version, review

    @staticmethod
    async def _verify_warning_signatures(
        session: AsyncSession, validation: ValidationResult, review: ReviewRecord
    ) -> None:
        current_signatures = {
            (item.rule_id, item.rule_version, item.field_path)
            for item in validation.issues
            if item.severity == "warning"
        }
        acknowledged = list(
            (
                await session.scalars(
                    select(ValidationIssue).where(
                        ValidationIssue.id.in_(review.acknowledged_warning_ids)
                    )
                )
            ).all()
        )
        acknowledged_signatures = {
            (item.rule_id, item.rule_version, item.field_path) for item in acknowledged
        }
        if current_signatures != acknowledged_signatures:
            raise WorkflowError("warnings_changed", "当前警告与批准时的确认不一致")

    @staticmethod
    async def _version(
        session: AsyncSession, plan_id: uuid.UUID, version_number: int
    ) -> TestPlanVersion:
        version = await session.scalar(
            select(TestPlanVersion).where(
                TestPlanVersion.test_plan_id == plan_id,
                TestPlanVersion.version_number == version_number,
            )
        )
        if version is None:
            raise RuntimeError("计划版本不存在")
        return version

    @staticmethod
    async def _locked_plan(session: AsyncSession, plan_id: uuid.UUID) -> TestPlan:
        plan = await session.scalar(
            select(TestPlan).where(TestPlan.id == plan_id).with_for_update()
        )
        if plan is None:
            raise WorkflowError("test_plan_not_found", "测试计划不存在")
        return plan

    @staticmethod
    def _validate_operator(operator_name: str, operator_employee_id: str) -> None:
        if (
            not operator_name.strip()
            or len(operator_employee_id) != 9
            or not operator_employee_id.isdigit()
        ):
            raise WorkflowError("invalid_operator", "操作者姓名必填，工号必须为 9 位数字")  # noqa: RUF001

    @staticmethod
    def _verify_repeated_confirmation(
        submission: Submission,
        payload_sha256: str,
        operator_name: str,
        operator_employee_id: str,
    ) -> None:
        if (
            submission.payload_sha256 != payload_sha256
            or submission.operator_name != operator_name.strip()
            or submission.operator_employee_id != operator_employee_id
        ):
            raise WorkflowError("confirmation_already_used", "该报文已由另一份确认声明处理")

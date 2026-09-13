from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_workflow.application.rules import RuleEngine
from email_workflow.core.canonical import canonical_sha256
from email_workflow.domain.plan import FieldMetadata, TestPlanContent
from email_workflow.infrastructure.models import (
    EvidenceSegment,
    ReviewRecord,
    TestPlan,
    TestPlanVersion,
    ValidationIssue,
    ValidationRun,
)


class WorkflowError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class VersionResult:
    version: TestPlanVersion
    created: bool


@dataclass(frozen=True, slots=True)
class ValidationResult:
    run: ValidationRun
    issues: list[ValidationIssue]


class PlanWorkflowService:
    EDITABLE_STATES: ClassVar[set[str]] = {
        "draft",
        "revision_requested",
        "approved",
        "submission_failed",
    }
    TOP_METADATA_FIELDS: ClassVar[set[str]] = {
        "plan_name",
        "project_name",
        "project_code",
        "requirement_ids",
        "test_type",
        "test_stage",
        "test_round",
        "priority",
        "test_version",
        "planned_start_date",
        "planned_end_date",
        "objective",
        "scope",
        "environment",
        "risks",
        "dependencies",
        "notes",
    }
    DETAIL_METADATA_FIELDS: ClassVar[set[str]] = {
        "domain_key",
        "domain_name",
        "domain_code",
        "owner_name",
        "owner_employee_id",
        "execution_start_date",
        "execution_end_date",
        "scope",
    }

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        rule_engine: RuleEngine,
    ) -> None:
        self.session_factory = session_factory
        self.rule_engine = rule_engine

    async def create_version(
        self, plan_id: uuid.UUID, *, base_version: int, content: TestPlanContent
    ) -> VersionResult:
        async with self.session_factory() as session, session.begin():
            plan = await self._locked_plan(session, plan_id)
            if plan.current_version != base_version:
                raise WorkflowError("base_version_conflict", "计划已被其他操作更新，请刷新后重试")  # noqa: RUF001
            if plan.status not in self.EDITABLE_STATES:
                raise WorkflowError("plan_content_locked", "当前状态不允许修改计划内容")
            current = await self._version(session, plan.id, plan.current_version)
            normalized = self._normalize_provenance(
                TestPlanContent.model_validate(current.content), content
            )
            serialized = normalized.model_dump(mode="json")
            content_sha256 = canonical_sha256(serialized)
            if content_sha256 == current.content_sha256:
                return VersionResult(version=current, created=False)
            next_version = TestPlanVersion(
                id=uuid.uuid4(),
                test_plan_id=plan.id,
                version_number=plan.current_version + 1,
                content=serialized,
                content_sha256=content_sha256,
                domain_catalog_version=current.domain_catalog_version,
                value_catalog_version=current.value_catalog_version,
                prompt_version=current.prompt_version,
                prompt_sha256=current.prompt_sha256,
            )
            session.add(next_version)
            plan.current_version += 1
            plan.status = "draft"
            plan.updated_at = datetime.now(UTC)
            await session.flush()
            return VersionResult(version=next_version, created=True)

    async def validate(self, plan_id: uuid.UUID) -> ValidationResult:
        async with self.session_factory() as session, session.begin():
            plan = await self._plan(session, plan_id)
            version = await self._version(session, plan.id, plan.current_version)
            return await self._run_validation(session, plan, version)

    async def submit_for_review(self, plan_id: uuid.UUID) -> ValidationResult:
        async with self.session_factory() as session:
            async with session.begin():
                plan = await self._locked_plan(session, plan_id)
                if plan.status not in {"draft", "revision_requested"}:
                    raise WorkflowError("invalid_plan_state", "当前状态不能送审")
                version = await self._version(session, plan.id, plan.current_version)
                result = await self._run_validation(session, plan, version)
                blocked = result.run.blocking_count > 0
                if not blocked:
                    plan.status = "pending_review"
                    plan.updated_at = datetime.now(UTC)
            if blocked:
                raise WorkflowError("validation_blocked", "存在阻断问题，计划未进入待审核状态")  # noqa: RUF001
            return result

    async def review(
        self,
        plan_id: uuid.UUID,
        *,
        decision: str,
        operator_name: str,
        operator_employee_id: str,
        comment: str | None,
        validation_run_id: uuid.UUID | None,
        acknowledged_warning_ids: list[uuid.UUID],
    ) -> ReviewRecord:
        async with self.session_factory() as session, session.begin():
            plan = await self._locked_plan(session, plan_id)
            version = await self._version(session, plan.id, plan.current_version)
            existing = await session.scalar(
                select(ReviewRecord).where(ReviewRecord.test_plan_version_id == version.id)
            )
            signature = (
                decision,
                operator_name.strip(),
                operator_employee_id,
                (comment or "").strip(),
                set(acknowledged_warning_ids),
            )
            if existing is not None:
                existing_signature = (
                    existing.decision,
                    existing.operator_name,
                    existing.operator_employee_id,
                    (existing.comment or "").strip(),
                    set(existing.acknowledged_warning_ids),
                )
                if signature == existing_signature:
                    return existing
                raise WorkflowError("review_already_decided", "当前版本已有审核决定")
            if plan.status != "pending_review":
                raise WorkflowError("invalid_plan_state", "只有待审核计划可以提交审核决定")
            if (
                not operator_name.strip()
                or not operator_employee_id.isdigit()
                or len(operator_employee_id) != 9
            ):
                raise WorkflowError("invalid_operator", "操作者姓名必填，工号必须为 9 位数字")  # noqa: RUF001
            if decision == "revision_requested" and not (comment or "").strip():
                raise WorkflowError("review_comment_required", "退回修改时必须填写审核意见")
            if decision not in {"approved", "revision_requested"}:
                raise WorkflowError("invalid_review_decision", "不支持该审核决定")
            if decision == "approved":
                await self._verify_approval_warnings(
                    session,
                    plan=plan,
                    version=version,
                    validation_run_id=validation_run_id,
                    acknowledged_warning_ids=acknowledged_warning_ids,
                )
            record = ReviewRecord(
                id=uuid.uuid4(),
                test_plan_id=plan.id,
                test_plan_version_id=version.id,
                content_sha256=version.content_sha256,
                operator_name=operator_name.strip(),
                operator_employee_id=operator_employee_id,
                decision=decision,
                comment=(comment or "").strip() or None,
                acknowledged_warning_ids=acknowledged_warning_ids,
            )
            session.add(record)
            plan.status = decision
            plan.updated_at = datetime.now(UTC)
            await session.flush()
            return record

    async def reviews(self, plan_id: uuid.UUID) -> list[ReviewRecord]:
        async with self.session_factory() as session:
            await self._plan(session, plan_id)
            statement = (
                select(ReviewRecord)
                .where(ReviewRecord.test_plan_id == plan_id)
                .order_by(ReviewRecord.created_at.desc(), ReviewRecord.id)
            )
            return list((await session.scalars(statement)).all())

    async def _run_validation(
        self, session: AsyncSession, plan: TestPlan, version: TestPlanVersion
    ) -> ValidationResult:
        evidence = list(
            (
                await session.scalars(
                    select(EvidenceSegment).where(
                        EvidenceSegment.source_item_id == plan.source_email_id
                    )
                )
            ).all()
        )
        findings = self.rule_engine.validate(
            TestPlanContent.model_validate(version.content),
            source_email_id=plan.source_email_id,
            evidence_segments=evidence,
        )
        blocking_count = sum(item.severity == "blocking" for item in findings)
        warning_count = sum(item.severity == "warning" for item in findings)
        run = ValidationRun(
            id=uuid.uuid4(),
            test_plan_id=plan.id,
            test_plan_version_id=version.id,
            content_sha256=version.content_sha256,
            rule_set_version=self.rule_engine.rule_set.version,
            status="failed" if blocking_count else "passed",
            blocking_count=blocking_count,
            warning_count=warning_count,
            finished_at=datetime.now(UTC),
        )
        issues = [
            ValidationIssue(
                id=uuid.uuid4(),
                validation_run_id=run.id,
                rule_id=finding.rule_id,
                rule_version=finding.rule_version,
                severity=finding.severity,
                field_path=finding.field_path,
                message=finding.message,
                suggestion=finding.suggestion,
            )
            for finding in findings
        ]
        session.add(run)
        await session.flush()
        session.add_all(issues)
        await session.flush()
        return ValidationResult(run=run, issues=issues)

    async def _verify_approval_warnings(
        self,
        session: AsyncSession,
        *,
        plan: TestPlan,
        version: TestPlanVersion,
        validation_run_id: uuid.UUID | None,
        acknowledged_warning_ids: list[uuid.UUID],
    ) -> None:
        if validation_run_id is None:
            raise WorkflowError("validation_run_required", "批准时必须引用送审校验结果")
        run = await session.get(ValidationRun, validation_run_id)
        if (
            run is None
            or run.test_plan_id != plan.id
            or run.test_plan_version_id != version.id
            or run.content_sha256 != version.content_sha256
            or run.status != "passed"
        ):
            raise WorkflowError("stale_validation_run", "校验结果与当前计划版本不一致")
        warning_ids = set(
            (
                await session.scalars(
                    select(ValidationIssue.id).where(
                        ValidationIssue.validation_run_id == run.id,
                        ValidationIssue.severity == "warning",
                    )
                )
            ).all()
        )
        acknowledged = set(acknowledged_warning_ids)
        if acknowledged != warning_ids:
            raise WorkflowError("warnings_not_acknowledged", "必须逐条确认当前版本的全部警告")

    @staticmethod
    async def _plan(session: AsyncSession, plan_id: uuid.UUID) -> TestPlan:
        plan = await session.get(TestPlan, plan_id)
        if plan is None:
            raise WorkflowError("test_plan_not_found", "测试计划不存在")
        return plan

    @classmethod
    async def _locked_plan(cls, session: AsyncSession, plan_id: uuid.UUID) -> TestPlan:
        plan = await session.scalar(
            select(TestPlan).where(TestPlan.id == plan_id).with_for_update()
        )
        if plan is None:
            raise WorkflowError("test_plan_not_found", "测试计划不存在")
        return plan

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
            raise RuntimeError("计划当前版本不存在")
        return version

    @staticmethod
    def _normalize_provenance(
        previous: TestPlanContent, proposed: TestPlanContent
    ) -> TestPlanContent:
        result = proposed.model_copy(deep=True)
        result.field_metadata = {
            key: value for key, value in result.field_metadata.items() if hasattr(result, key)
        }
        top_metadata_keys = (
            set(previous.field_metadata)
            | set(result.field_metadata)
            | PlanWorkflowService.TOP_METADATA_FIELDS
        )
        for field_name in top_metadata_keys:
            if not hasattr(result, field_name):
                continue
            metadata = result.field_metadata.get(field_name) or previous.field_metadata.get(
                field_name
            )
            references = metadata.evidence_references if metadata is not None else []
            if field_name in previous.field_metadata and getattr(
                previous, field_name, None
            ) == getattr(result, field_name, None):
                result.field_metadata[field_name] = previous.field_metadata[field_name]
            else:
                result.field_metadata[field_name] = FieldMetadata(
                    provenance="user_provided",
                    evidence_references=references,
                )
        for index, detail in enumerate(result.details):
            old_detail = previous.details[index] if index < len(previous.details) else None
            detail.field_metadata = {
                key: value for key, value in detail.field_metadata.items() if hasattr(detail, key)
            }
            detail_metadata_keys = (
                set(detail.field_metadata) | PlanWorkflowService.DETAIL_METADATA_FIELDS
            )
            if old_detail is not None:
                detail_metadata_keys.update(old_detail.field_metadata)
            for field_name in detail_metadata_keys:
                if not hasattr(detail, field_name):
                    continue
                metadata = detail.field_metadata.get(field_name)
                if metadata is None and old_detail is not None:
                    metadata = old_detail.field_metadata.get(field_name)
                references = metadata.evidence_references if metadata is not None else []
                if (
                    old_detail is not None
                    and field_name in old_detail.field_metadata
                    and getattr(old_detail, field_name, None) == getattr(detail, field_name, None)
                ):
                    detail.field_metadata[field_name] = old_detail.field_metadata[field_name]
                else:
                    detail.field_metadata[field_name] = FieldMetadata(
                        provenance="user_provided",
                        evidence_references=references,
                    )
            for requirement_index, requirement in enumerate(detail.requirements):
                old = (
                    old_detail.requirements[requirement_index]
                    if old_detail is not None and requirement_index < len(old_detail.requirements)
                    else None
                )
                if old is None or requirement.text != old.text:
                    requirement.provenance = "user_provided"
                else:
                    requirement.provenance = old.provenance
                    requirement.evidence_references = old.evidence_references
            for case_index, case in enumerate(detail.test_cases):
                old_case = (
                    old_detail.test_cases[case_index]
                    if old_detail is not None and case_index < len(old_detail.test_cases)
                    else None
                )
                if old_case is None or case.model_dump(
                    exclude={"provenance", "evidence_references"}
                ) != old_case.model_dump(exclude={"provenance", "evidence_references"}):
                    case.provenance = "user_provided"
                else:
                    case.provenance = old_case.provenance
                    case.evidence_references = old_case.evidence_references
        return result

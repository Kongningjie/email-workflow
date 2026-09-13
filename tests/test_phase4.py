from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from email_workflow.application.connector import (
    ConnectorIndeterminate,
    ConnectorRejected,
)
from email_workflow.application.mapping import PlatformPayloadMapper
from email_workflow.application.rules import RuleEngine
from email_workflow.application.submissions import SubmissionService
from email_workflow.application.workflow import PlanWorkflowService, WorkflowError
from email_workflow.core.canonical import canonical_bytes, canonical_sha256
from email_workflow.core.catalogs import load_mapping_document, load_rule_set
from email_workflow.domain.platform import (
    GatewaySubmissionReceipt,
    GatewaySubmissionStatus,
    GatewayValidationResponse,
    PlatformPlanPayload,
)
from email_workflow.infrastructure.database import create_engine, create_session_factory
from email_workflow.infrastructure.mock_connector import MockTestManagementConnector
from email_workflow.infrastructure.models import Base, TestPlan
from mock_gateway.main import app as gateway_app
from mock_gateway.main import reset_mock_state
from tests.test_phase3 import catalogs, make_content, make_segment, seed_plan


def mapper() -> PlatformPayloadMapper:
    return PlatformPayloadMapper(
        mapping=load_mapping_document(Path("config/mappings/mock-platform-v1.yaml")),
        catalogs=catalogs(),
    )


def phase4_workflow(
    session_factory: async_sessionmaker[AsyncSession],
) -> PlanWorkflowService:
    payload_mapper = mapper()
    return PlanWorkflowService(
        session_factory=session_factory,
        rule_engine=RuleEngine(
            rule_set=load_rule_set(Path("config/rules/v1.yaml")),
            catalogs=catalogs(),
            payload_mapper=payload_mapper,
        ),
    )


@pytest_asyncio.fixture
async def phase4_database() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("未配置独立 PostgreSQL 测试库")
    if not database_url.rstrip("/").endswith("email_workflow_test"):
        pytest.fail("TEST_DATABASE_URL 必须指向 email_workflow_test")
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine, create_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def approve_plan(service: PlanWorkflowService, plan_id: uuid.UUID) -> None:
    validation = await service.submit_for_review(plan_id)
    warning_ids = [issue.id for issue in validation.issues if issue.severity == "warning"]
    await service.review(
        plan_id,
        decision="approved",
        operator_name="王芳",
        operator_employee_id="001234567",
        comment=None,
        validation_run_id=validation.run.id,
        acknowledged_warning_ids=warning_ids,
    )


class FakeConnector:
    def __init__(
        self,
        *,
        submit_outcomes: list[str] | None = None,
        query_status: str = "not_found",
    ) -> None:
        self.submit_outcomes = submit_outcomes or ["success"]
        self.query_status = query_status
        self.calls: list[tuple[str, uuid.UUID]] = []

    async def validate_payload(self, payload: PlatformPlanPayload) -> GatewayValidationResponse:
        return GatewayValidationResponse(valid=True)

    async def submit_plan(
        self,
        payload: PlatformPlanPayload,
        *,
        idempotency_key: str,
        submission_request_id: uuid.UUID,
    ) -> GatewaySubmissionReceipt:
        self.calls.append((idempotency_key, submission_request_id))
        outcome = self.submit_outcomes.pop(0)
        if outcome == "rejected":
            raise ConnectorRejected(422, "模拟明确拒绝")
        if outcome == "unknown":
            raise ConnectorIndeterminate("模拟结果未知")
        return GatewaySubmissionReceipt(
            status="submitted",
            external_request_id=f"REQ-{submission_request_id.hex[:8]}",
            external_plan_id=f"PLAN-{submission_request_id.hex[:8]}",
        )

    async def get_submission_status(
        self,
        submission_request_id: uuid.UUID,
        *,
        idempotency_key: str,
    ) -> GatewaySubmissionStatus:
        return GatewaySubmissionStatus(
            status=self.query_status,
            external_request_id=("REQ-reconciled" if self.query_status == "submitted" else None),
            external_plan_id=("PLAN-reconciled" if self.query_status == "submitted" else None),
            safe_summary="模拟对账结果",
        )


def test_platform_mapping_excludes_internal_and_evidence_fields() -> None:
    source_id = uuid.uuid4()
    content = make_content(make_segment(source_id))
    payload = mapper().map(plan_id=uuid.uuid4(), version_number=3, content=content)
    serialized = payload.model_dump(mode="json", by_alias=True)
    flattened = str(serialized)

    assert serialized["contractVersion"] == "1.0"
    assert serialized["testType"] == "FUNCTIONAL"
    assert serialized["domains"][0]["domainCode"] == "COMM"
    assert "evidence" not in flattened
    assert "open_questions" not in flattened
    assert canonical_sha256(serialized) == canonical_sha256(serialized)


def test_canonical_json_vector_and_platform_limit_rules() -> None:
    assert canonical_bytes({"b": 1, "a": "测试"}) == '{"a":"测试","b":1}'.encode()
    source_id = uuid.uuid4()
    segment = make_segment(source_id)
    content = make_content(segment)
    engine = RuleEngine(
        rule_set=load_rule_set(Path("config/rules/v1.yaml")),
        catalogs=catalogs(),
        payload_mapper=mapper(),
    )
    content.plan_name = "测" * 180
    near_ids = {
        item.rule_id
        for item in engine.validate(content, source_email_id=source_id, evidence_segments=[segment])
    }
    assert "platform.near_limit" in near_ids
    content.plan_name = "测" * 201
    over_ids = {
        item.rule_id
        for item in engine.validate(content, source_email_id=source_id, evidence_segments=[segment])
    }
    assert "platform.payload_contract" in over_ids


def test_mapping_profile_collection_limits_are_enforced() -> None:
    payload_mapper = mapper()
    source_id = uuid.uuid4()
    content = make_content(make_segment(source_id))
    mapping = payload_mapper.mapping.model_copy(deep=True)
    mapping.limits["max_domains"] = 0
    mapping.limits["max_cases_total"] = 0
    mapping.limits["max_cases_per_domain"] = 0
    mapping.limits["max_steps_per_case"] = 0
    constrained_mapper = PlatformPayloadMapper(mapping=mapping, catalogs=catalogs())

    hard_limit_paths = {
        finding.field_path
        for finding in constrained_mapper.inspect_limits(content)
        if not finding.near_limit
    }

    assert {
        "details",
        "details[].test_cases",
        "details[0].test_cases",
        "details[0].test_cases[0].steps",
    } <= hard_limit_paths


@pytest.mark.asyncio
async def test_mock_gateway_hmac_idempotency_and_unknown_reconciliation() -> None:
    reset_mock_state()
    source_id = uuid.uuid4()
    payload = mapper().map(
        plan_id=uuid.uuid4(), version_number=1, content=make_content(make_segment(source_id))
    )
    transport = httpx.ASGITransport(app=gateway_app)
    overloaded = payload.model_dump(mode="json", by_alias=True)
    overloaded["domains"] = overloaded["domains"] * 11
    async with httpx.AsyncClient(base_url="http://gateway.test", transport=transport) as client:
        validation_response = await client.post(
            "/mock/v1/test-plans/validate", json=overloaded
        )
    assert validation_response.status_code == 200
    assert validation_response.json()["valid"] is False
    connector = MockTestManagementConnector(
        base_url="http://gateway.test",
        key_id="local-demo",
        hmac_secret="replace-with-a-local-demo-secret",
        scenario="unknown_then_success",
        transport=transport,
    )
    request_id = uuid.uuid4()
    with pytest.raises(ConnectorIndeterminate):
        await connector.submit_plan(
            payload, idempotency_key="a" * 64, submission_request_id=request_id
        )
    status = await connector.get_submission_status(request_id, idempotency_key="a" * 64)
    assert status.status == "submitted"

    connector.scenario = None
    receipt = await connector.submit_plan(
        payload, idempotency_key="a" * 64, submission_request_id=request_id
    )
    assert receipt.deduplicated is True
    bad_connector = MockTestManagementConnector(
        base_url="http://gateway.test",
        key_id="local-demo",
        hmac_secret="wrong-secret",
        transport=transport,
    )
    with pytest.raises(ConnectorRejected) as captured:
        await bad_connector.submit_plan(
            payload, idempotency_key="b" * 64, submission_request_id=uuid.uuid4()
        )
    assert captured.value.status_code == 401
    expired_connector = MockTestManagementConnector(
        base_url="http://gateway.test",
        key_id="local-demo",
        hmac_secret="replace-with-a-local-demo-secret",
        clock=lambda: 1,
        transport=transport,
    )
    with pytest.raises(ConnectorRejected) as expired:
        await expired_connector.submit_plan(
            payload, idempotency_key="c" * 64, submission_request_id=uuid.uuid4()
        )
    assert expired.value.status_code == 401


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_preview_confirm_success_and_token_idempotency(
    phase4_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, session_factory = phase4_database
    plan_id, content = await seed_plan(session_factory)
    workflow = phase4_workflow(session_factory)
    await approve_plan(workflow, plan_id)
    connector = FakeConnector()
    tokens = iter(("t" * 43, "v" * 43))
    service = SubmissionService(
        session_factory=session_factory,
        workflow_service=workflow,
        mapper=mapper(),
        connector=connector,
        token_factory=lambda: next(tokens),
    )

    preview = await service.create_preview(plan_id)
    second_preview = await service.create_preview(plan_id)
    assert preview.preview.payload_sha256 == canonical_sha256(preview.preview.payload)
    assert "evidence" not in preview.canonical_json
    with pytest.raises(WorkflowError, match="哈希不一致"):
        await service.confirm_submission(
            plan_id,
            confirmation_token=preview.confirmation_token,
            payload_sha256="0" * 64,
            operator_name="李明",
            operator_employee_id="009876543",
        )
    submission = await service.confirm_submission(
        plan_id,
        confirmation_token=preview.confirmation_token,
        payload_sha256=preview.preview.payload_sha256,
        operator_name="李明",
        operator_employee_id="009876543",
    )
    repeated = await service.confirm_submission(
        plan_id,
        confirmation_token=preview.confirmation_token,
        payload_sha256=preview.preview.payload_sha256,
        operator_name="李明",
        operator_employee_id="009876543",
    )
    same_target = await service.confirm_submission(
        plan_id,
        confirmation_token=second_preview.confirmation_token,
        payload_sha256=second_preview.preview.payload_sha256,
        operator_name="李明",
        operator_employee_id="009876543",
    )
    assert submission.status == "submitted" and repeated.id == submission.id
    assert same_target.id == submission.id
    assert len(connector.calls) == 1
    with pytest.raises(WorkflowError, match="确认声明"):
        await service.confirm_submission(
            plan_id,
            confirmation_token=preview.confirmation_token,
            payload_sha256=preview.preview.payload_sha256,
            operator_name="另一位操作者",
            operator_employee_id="000000001",
        )
    async with session_factory() as session:
        plan = await session.get(TestPlan, plan_id)
    assert plan is not None and plan.status == "submitted"
    with pytest.raises(WorkflowError, match="不允许修改"):
        await workflow.create_version(plan_id, base_version=1, content=content)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_unknown_requires_not_found_before_retry_and_reuses_identity(
    phase4_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, session_factory = phase4_database
    plan_id, _ = await seed_plan(session_factory)
    workflow = phase4_workflow(session_factory)
    await approve_plan(workflow, plan_id)
    connector = FakeConnector(submit_outcomes=["unknown", "success"], query_status="not_found")
    service = SubmissionService(
        session_factory=session_factory,
        workflow_service=workflow,
        mapper=mapper(),
        connector=connector,
        token_factory=lambda: "u" * 43,
    )
    preview = await service.create_preview(plan_id)
    submission = await service.confirm_submission(
        plan_id,
        confirmation_token=preview.confirmation_token,
        payload_sha256=preview.preview.payload_sha256,
        operator_name="李明",
        operator_employee_id="009876543",
    )
    assert submission.status == "unknown"
    with pytest.raises(WorkflowError, match="not_found"):
        await service.retry(submission.id)
    reconciled = await service.reconcile(submission.id)
    assert reconciled.status == "unknown"
    retried = await service.retry(submission.id)
    assert retried.status == "submitted"
    assert connector.calls[0] == connector.calls[1]


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("query_status", ["submitted", "submission_failed"])
async def test_unknown_reconciliation_reaches_explicit_result(
    phase4_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    query_status: str,
) -> None:
    _, session_factory = phase4_database
    plan_id, _ = await seed_plan(session_factory)
    workflow = phase4_workflow(session_factory)
    await approve_plan(workflow, plan_id)
    connector = FakeConnector(submit_outcomes=["unknown"], query_status=query_status)
    service = SubmissionService(
        session_factory=session_factory,
        workflow_service=workflow,
        mapper=mapper(),
        connector=connector,
        token_factory=lambda: "q" * 43,
    )
    preview = await service.create_preview(plan_id)
    submission = await service.confirm_submission(
        plan_id,
        confirmation_token=preview.confirmation_token,
        payload_sha256=preview.preview.payload_sha256,
        operator_name="李明",
        operator_employee_id="009876543",
    )
    reconciled = await service.reconcile(submission.id)
    assert reconciled.status == query_status


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_explicit_rejection_is_terminal_failure(
    phase4_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, session_factory = phase4_database
    plan_id, content = await seed_plan(session_factory)
    workflow = phase4_workflow(session_factory)
    await approve_plan(workflow, plan_id)
    service = SubmissionService(
        session_factory=session_factory,
        workflow_service=workflow,
        mapper=mapper(),
        connector=FakeConnector(submit_outcomes=["rejected"]),
        token_factory=lambda: "r" * 43,
    )
    preview = await service.create_preview(plan_id)
    submission = await service.confirm_submission(
        plan_id,
        confirmation_token=preview.confirmation_token,
        payload_sha256=preview.preview.payload_sha256,
        operator_name="李明",
        operator_employee_id="009876543",
    )
    assert submission.status == "submission_failed"
    content.notes = "平台拒绝后修改业务字段"
    version = await workflow.create_version(plan_id, base_version=1, content=content)
    assert version.created and version.version.version_number == 2
    async with session_factory() as session:
        plan = await session.get(TestPlan, plan_id)
    assert plan is not None and plan.status == "draft"

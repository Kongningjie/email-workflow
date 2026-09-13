from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from email_workflow.application.extraction import (
    CatalogBundle,
    EvidenceRebuilder,
    ExtractionFailure,
    ExtractionValidator,
    FakeExtractor,
    TestPlanDraftBuilder,
)
from email_workflow.core.catalogs import load_catalog
from email_workflow.domain.email import ParsedEmail
from email_workflow.domain.plan import ExtractionRequest
from email_workflow.infrastructure.models import EvidenceSegment, ImportedEmail
from email_workflow.infrastructure.storage import ImportStorage
from tests.factories import make_extraction_payload


def catalog_bundle() -> CatalogBundle:
    config = Path("config")
    return CatalogBundle(
        domains=load_catalog(config / "domains/v1.yaml"),
        test_types=load_catalog(config / "values/test-types-v1.yaml"),
        test_stages=load_catalog(config / "values/test-stages-v1.yaml"),
        priorities=load_catalog(config / "values/priorities-v1.yaml"),
    )


def evidence_segment(text: str = "Atlas 通信测试要求") -> EvidenceSegment:
    return EvidenceSegment(
        id=uuid.uuid4(),
        source_item_id=uuid.uuid4(),
        section_type="subject",
        segment_index=0,
        start_offset=0,
        end_offset=len(text),
        safe_excerpt=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=90),
        purged_at=None,
    )


def test_builder_maps_catalogs_rebuilds_references_and_applies_allowed_defaults() -> None:
    segment = evidence_segment()
    content = TestPlanDraftBuilder(
        catalogs=catalog_bundle(),
        evidence_by_temporary_id={"evidence-0001": segment},
        email_subject="Atlas 通信测试要求",
    ).build(make_extraction_payload())

    assert content.plan_name == "Atlas 通信测试要求"
    assert content.field_metadata["plan_name"].provenance == "derived"
    assert content.test_type == "functional"
    assert content.test_stage == "system"
    assert content.priority == "high"
    assert content.details[0].domain_key == "communication"
    assert content.details[0].domain_name == "通信"
    assert content.details[0].domain_code == "COMM"
    assert content.details[0].execution_start_date == content.planned_start_date
    assert content.details[0].field_metadata["execution_start_date"].provenance == "derived"
    assert content.details[0].test_cases[0].domain_key == "communication"
    assert content.details[0].test_cases[0].evidence_references[0].evidence_segment_id == segment.id


def test_unknown_evidence_id_rejects_entire_extraction() -> None:
    payload = make_extraction_payload("evidence-9999")
    with pytest.raises(ExtractionFailure, match="unknown_evidence_id"):
        ExtractionValidator.validate_evidence_ids(payload, {"evidence-0001"})


def test_case_without_any_evidence_is_excluded_with_question() -> None:
    payload = make_extraction_payload()
    test_case = payload.details[0].test_cases[0]
    test_case.evidence_ids = []
    test_case.title.evidence_ids = []
    test_case.objective.evidence_ids = []
    test_case.preconditions.evidence_ids = []
    test_case.expected_result.evidence_ids = []
    test_case.priority.evidence_ids = []
    content = TestPlanDraftBuilder(
        catalogs=catalog_bundle(),
        evidence_by_temporary_id={"evidence-0001": evidence_segment()},
        email_subject=None,
    ).build(payload)

    assert content.details[0].test_cases == []
    assert any("没有邮件证据" in question for question in content.open_questions)


def test_fact_without_evidence_is_cleared_instead_of_being_accepted() -> None:
    payload = make_extraction_payload()
    payload.project_code.evidence_ids = []
    payload.details[0].owner_employee_id.evidence_ids = []
    content = TestPlanDraftBuilder(
        catalogs=catalog_bundle(),
        evidence_by_temporary_id={"evidence-0001": evidence_segment()},
        email_subject=None,
    ).build(payload)

    assert content.project_code == ""
    assert content.details[0].owner_employee_id == ""
    assert content.field_metadata["project_code"].provenance == "unresolved"
    assert "owner_employee_id" in content.details[0].unresolved_fields
    assert any("缺少合法邮件证据" in question for question in content.open_questions)


def test_schema_enforces_step_limit() -> None:
    payload = make_extraction_payload().model_dump(mode="python")
    payload["details"][0]["test_cases"][0]["steps"] = [
        {"step_number": index + 1, "action": "执行操作"} for index in range(21)
    ]
    with pytest.raises(ValidationError):
        type(make_extraction_payload()).model_validate(payload)


def test_schema_rejects_case_without_steps() -> None:
    payload = make_extraction_payload().model_dump(mode="python")
    payload["details"][0]["test_cases"][0]["steps"] = []
    with pytest.raises(ValidationError):
        type(make_extraction_payload()).model_validate(payload)


def test_evidence_rebuilder_rejects_tampered_excerpt(tmp_path: Path) -> None:
    import_id = uuid.uuid4()
    storage = ImportStorage(tmp_path)
    parsed = ParsedEmail(
        subject="主题",
        sender="sender@example.test",
        recipients=("qa@example.test",),
        sent_at=None,
        current_body="可信正文",
        quoted_body="",
    )
    storage.write_import(import_id, b"raw", parsed)
    imported = ImportedEmail(
        id=import_id,
        original_filename="fixture.eml",
        subject=parsed.subject,
        sender=parsed.sender,
        recipients=list(parsed.recipients),
        sent_at=None,
        content_sha256="0" * 64,
        parse_status="parsed",
        extraction_status="extracting",
        safe_error_summary=None,
        raw_expires_at=datetime.now(UTC) + timedelta(days=1),
        purged_at=None,
    )
    segment = evidence_segment("可信正文")
    segment.source_item_id = import_id
    segment.section_type = "current_body"
    segment.safe_excerpt = "被篡改正文"

    with pytest.raises(ExtractionFailure, match="evidence_hash_mismatch"):
        EvidenceRebuilder(storage).validate(imported, [segment])


@pytest.mark.asyncio
async def test_fake_extractor_is_called_once_and_supports_failure() -> None:
    request = ExtractionRequest(
        evidence=[],
        allowed_domains={},
        allowed_test_types={},
        allowed_test_stages={},
        allowed_priorities={},
    )
    extractor = FakeExtractor(make_extraction_payload())
    assert await extractor.extract(request) == make_extraction_payload()
    assert extractor.call_count == 1

    failing = FakeExtractor(failure_code="timeout")
    with pytest.raises(ExtractionFailure, match="timeout"):
        await failing.extract(request)
    assert failing.call_count == 1

    unexpected = FakeExtractor(unexpected_exception=RuntimeError("simulated"))
    with pytest.raises(RuntimeError, match="simulated"):
        await unexpected.extract(request)
    assert unexpected.call_count == 1

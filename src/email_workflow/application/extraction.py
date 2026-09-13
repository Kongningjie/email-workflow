from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Protocol

from email_workflow.core.catalogs import Catalog, CatalogItem
from email_workflow.domain.email import SectionType
from email_workflow.domain.plan import (
    EvidenceReference,
    ExtractedDomain,
    ExtractedList,
    ExtractionPayload,
    ExtractionRequest,
    FieldMetadata,
    RequirementContent,
    TestCaseContent,
    TestPlanContent,
    TestPlanDetailContent,
)
from email_workflow.infrastructure.models import EvidenceSegment, ImportedEmail
from email_workflow.infrastructure.storage import ImportStorage


class ExtractionFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StructuredRequirementExtractor(Protocol):
    async def extract(self, request: ExtractionRequest) -> ExtractionPayload: ...


class FakeExtractor:
    def __init__(
        self,
        result: ExtractionPayload | None = None,
        *,
        failure_code: str | None = None,
        unexpected_exception: Exception | None = None,
    ) -> None:
        self.result = result
        self.failure_code = failure_code
        self.unexpected_exception = unexpected_exception
        self.call_count = 0

    async def extract(self, request: ExtractionRequest) -> ExtractionPayload:
        del request
        self.call_count += 1
        if self.unexpected_exception is not None:
            raise self.unexpected_exception
        if self.failure_code is not None:
            raise ExtractionFailure(self.failure_code)
        if self.result is None:
            raise ExtractionFailure("fake_result_missing")
        return self.result


class ExtractionValidator:
    @staticmethod
    def validate_evidence_ids(payload: ExtractionPayload, allowed_ids: set[str]) -> None:
        unknown = _collect_evidence_ids(payload.model_dump(mode="python")) - allowed_ids
        if unknown:
            raise ExtractionFailure("unknown_evidence_id")


class EvidenceRebuilder:
    def __init__(self, storage: ImportStorage) -> None:
        self.storage = storage

    def validate(self, imported: ImportedEmail, segments: list[EvidenceSegment]) -> None:
        sources = {
            SectionType.SUBJECT.value: imported.subject or "",
            SectionType.SENDER.value: imported.sender or "",
            SectionType.RECIPIENTS.value: "\n".join(imported.recipients),
            SectionType.SENT_AT.value: imported.sent_at.isoformat() if imported.sent_at else "",
            SectionType.CURRENT_BODY.value: self.storage.read_section(
                imported.id, SectionType.CURRENT_BODY
            ),
            SectionType.QUOTED_BODY.value: self.storage.read_section(
                imported.id, SectionType.QUOTED_BODY
            ),
        }
        for segment in segments:
            source = sources.get(segment.section_type)
            excerpt = segment.safe_excerpt
            if source is None or excerpt is None:
                raise ExtractionFailure("evidence_unavailable")
            if segment.start_offset < 0 or segment.end_offset > len(source):
                raise ExtractionFailure("evidence_boundary_invalid")
            rebuilt = source[segment.start_offset : segment.end_offset]
            digest = hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
            if rebuilt != excerpt or digest != segment.content_sha256:
                raise ExtractionFailure("evidence_hash_mismatch")


def _collect_evidence_ids(value: object) -> set[str]:
    if isinstance(value, dict):
        collected: set[str] = set()
        for key, child in value.items():
            if key == "evidence_ids" and isinstance(child, list):
                collected.update(item for item in child if isinstance(item, str))
            else:
                collected.update(_collect_evidence_ids(child))
        return collected
    if isinstance(value, list):
        collected = set()
        for child in value:
            collected.update(_collect_evidence_ids(child))
        return collected
    return set()


@dataclass(frozen=True, slots=True)
class CatalogBundle:
    domains: Catalog
    test_types: Catalog
    test_stages: Catalog
    priorities: Catalog

    @property
    def value_version(self) -> str:
        versions = {self.test_types.version, self.test_stages.version, self.priorities.version}
        if len(versions) != 1:
            raise ValueError("测试类型、阶段和优先级值域版本必须一致")
        return next(iter(versions))

    def extraction_request_catalogs(self) -> dict[str, dict[str, list[str]]]:
        return {
            "allowed_domains": _catalog_prompt_values(self.domains),
            "allowed_test_types": _catalog_prompt_values(self.test_types),
            "allowed_test_stages": _catalog_prompt_values(self.test_stages),
            "allowed_priorities": _catalog_prompt_values(self.priorities),
        }


def _catalog_prompt_values(catalog: Catalog) -> dict[str, list[str]]:
    return {item.key: [item.display_name, *item.aliases] for item in catalog.items if item.enabled}


class TestPlanDraftBuilder:
    _TOP_LEVEL_FIELDS = (
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
    )
    _FIELD_LABELS: ClassVar[dict[str, str]] = {
        "plan_name": "计划名称",
        "project_name": "项目名称",
        "project_code": "项目编码",
        "requirement_ids": "需求编号",
        "test_type": "测试类型",
        "test_stage": "测试阶段",
        "test_round": "测试轮次",
        "priority": "优先级",
        "test_version": "测试版本",
        "planned_start_date": "计划开始日期",
        "planned_end_date": "计划结束日期",
        "objective": "测试目标",
        "scope": "测试总体范围",
        "environment": "测试环境",
        "risks": "风险",
        "dependencies": "依赖",
        "notes": "备注",
    }

    def __init__(
        self,
        *,
        catalogs: CatalogBundle,
        evidence_by_temporary_id: dict[str, EvidenceSegment],
        email_subject: str | None,
    ) -> None:
        self.catalogs = catalogs
        self.evidence = evidence_by_temporary_id
        self.email_subject = (email_subject or "").strip()

    def build(self, extracted: ExtractionPayload) -> TestPlanContent:
        questions = list(
            dict.fromkeys(item.strip() for item in extracted.open_questions if item.strip())
        )
        trusted_text = {
            field: self._trusted_text(
                getattr(extracted, field), self._FIELD_LABELS[field], questions
            )
            for field in self._TOP_LEVEL_FIELDS
            if field not in {"requirement_ids", "risks", "dependencies"}
        }
        trusted_lists = {
            field: self._trusted_list(
                getattr(extracted, field), self._FIELD_LABELS[field], questions
            )
            for field in ("requirement_ids", "risks", "dependencies")
        }
        test_type = self._catalog_value(trusted_text["test_type"], self.catalogs.test_types)
        test_stage = self._catalog_value(trusted_text["test_stage"], self.catalogs.test_stages)
        priority = self._catalog_value(trusted_text["priority"], self.catalogs.priorities)
        for label, raw_value, resolved in (
            ("测试类型", trusted_text["test_type"], test_type),
            ("测试阶段", trusted_text["test_stage"], test_stage),
            ("优先级", trusted_text["priority"], priority),
        ):
            if raw_value.strip() and not resolved:
                questions.append(f"请确认无法识别的{label}：{raw_value.strip()}")

        planned_start_date = self._date_value(
            trusted_text["planned_start_date"], "计划开始日期", questions
        )
        planned_end_date = self._date_value(
            trusted_text["planned_end_date"], "计划结束日期", questions
        )
        plan_name = trusted_text["plan_name"]
        plan_name_is_derived = not plan_name and bool(self.email_subject)
        if plan_name_is_derived:
            plan_name = self.email_subject

        required_questions = (
            (not plan_name, "请填写计划名称。"),
            (
                not trusted_text["project_name"] and not trusted_text["project_code"],
                "请填写项目名称或项目编码。",
            ),
            (not test_type, "请确认测试类型。"),
            (not test_stage, "请确认测试阶段。"),
            (not priority, "请确认计划优先级。"),
            (not trusted_text["test_version"], "请填写测试版本。"),
            (planned_start_date is None, "请填写计划开始日期。"),
            (planned_end_date is None, "请填写计划结束日期。"),
            (not trusted_text["objective"], "请填写测试目标。"),
            (not trusted_text["scope"], "请填写测试总体范围。"),
            (not extracted.details, "请至少添加一个测试领域。"),
        )
        questions.extend(message for missing, message in required_questions if missing)

        details = [
            self._build_detail(item, planned_start_date, planned_end_date, questions)
            for item in extracted.details
        ]
        field_metadata = {
            field: self._field_metadata(getattr(extracted, field))
            for field in self._TOP_LEVEL_FIELDS
        }
        if plan_name_is_derived:
            field_metadata["plan_name"] = FieldMetadata(
                provenance="derived",
                evidence_references=self._references_for_section("subject"),
            )
        all_references = self._deduplicate_references(
            [
                reference
                for metadata in field_metadata.values()
                for reference in metadata.evidence_references
            ]
            + [reference for detail in details for reference in detail.evidence_references]
        )
        return TestPlanContent(
            plan_name=plan_name,
            project_name=trusted_text["project_name"],
            project_code=trusted_text["project_code"],
            requirement_ids=trusted_lists["requirement_ids"],
            test_type=test_type,
            test_stage=test_stage,
            test_round=trusted_text["test_round"],
            priority=priority,
            test_version=trusted_text["test_version"],
            planned_start_date=planned_start_date,
            planned_end_date=planned_end_date,
            objective=trusted_text["objective"],
            scope=trusted_text["scope"],
            environment=trusted_text["environment"],
            risks=trusted_lists["risks"],
            dependencies=trusted_lists["dependencies"],
            notes=trusted_text["notes"],
            open_questions=list(dict.fromkeys(questions)),
            evidence_references=all_references,
            details=details,
            field_metadata=field_metadata,
        )

    def blank(self, failure_code: str) -> TestPlanContent:
        empty = ExtractionPayload.model_validate(_blank_extraction_payload())
        empty.open_questions.append(f"结构化提取失败（{failure_code}），请人工填写并确认计划。")
        return self.build(empty)

    def _build_detail(
        self,
        extracted: ExtractedDomain,
        plan_start: date | None,
        plan_end: date | None,
        questions: list[str],
    ) -> TestPlanDetailContent:
        unresolved = list(
            dict.fromkeys(item.strip() for item in extracted.unresolved_fields if item.strip())
        )
        domain_key_value = self._trusted_text(extracted.domain_key, "测试领域", questions)
        owner_name = self._trusted_text(extracted.owner_name, "领域负责人", questions)
        owner_employee_id = self._trusted_text(extracted.owner_employee_id, "负责人工号", questions)
        scope = self._trusted_text(extracted.scope, "领域范围", questions)
        start_raw = self._trusted_text(
            extracted.execution_start_date, "领域执行开始日期", questions
        )
        end_raw = self._trusted_text(extracted.execution_end_date, "领域执行结束日期", questions)
        catalog_item = self._catalog_item(domain_key_value, self.catalogs.domains)
        if catalog_item is None:
            domain_key = ""
            domain_name = ""
            domain_code = ""
            unresolved.append("domain_key")
            if domain_key_value:
                questions.append(f"请确认无法识别的测试领域：{domain_key_value}")
        else:
            domain_key = catalog_item.key
            domain_name = catalog_item.display_name
            domain_code = catalog_item.platform_value

        start = self._date_value(start_raw, "领域执行开始日期", questions)
        end = self._date_value(end_raw, "领域执行结束日期", questions)
        start_derived = not start_raw.strip() and plan_start is not None
        end_derived = not end_raw.strip() and plan_end is not None
        if start_derived:
            start = plan_start
        if end_derived:
            end = plan_end

        requirements: list[RequirementContent] = []
        for requirement in extracted.requirements:
            references = self._references(requirement.evidence_ids)
            if requirement.text.strip() and references:
                requirements.append(
                    RequirementContent(
                        text=requirement.text.strip(),
                        evidence_references=references,
                        provenance="source",
                    )
                )
            elif requirement.text.strip():
                unresolved.append("requirements")
                questions.append("存在缺少邮件证据的需求描述，请人工确认。")

        test_cases: list[TestCaseContent] = []
        for test_case in extracted.test_cases:
            references = self._references(
                [
                    *test_case.evidence_ids,
                    *test_case.title.evidence_ids,
                    *test_case.objective.evidence_ids,
                    *test_case.preconditions.evidence_ids,
                    *test_case.test_data.evidence_ids,
                    *test_case.expected_result.evidence_ids,
                    *test_case.priority.evidence_ids,
                ]
            )
            if not references:
                questions.append("已排除一条没有邮件证据的模型建议用例，请人工确认是否补充。")
                continue
            trusted_case_priority = self._trusted_text(test_case.priority, "用例优先级", questions)
            case_priority = self._catalog_value(trusted_case_priority, self.catalogs.priorities)
            if trusted_case_priority and not case_priority:
                questions.append(f"请确认无法识别的用例优先级：{trusted_case_priority}")
            test_cases.append(
                TestCaseContent(
                    title=test_case.title.value.strip(),
                    objective=test_case.objective.value.strip(),
                    preconditions=self._clean_list(test_case.preconditions),
                    steps=test_case.steps,
                    test_data=test_case.test_data.value.strip(),
                    expected_result=test_case.expected_result.value.strip(),
                    priority=case_priority,
                    domain_key=domain_key,
                    evidence_references=references,
                    provenance=test_case.provenance,
                    open_questions=[
                        item.strip() for item in test_case.open_questions if item.strip()
                    ],
                )
            )

        for field, missing in (
            ("owner_name", not owner_name),
            ("owner_employee_id", not owner_employee_id),
            ("execution_start_date", start is None),
            ("execution_end_date", end is None),
            ("scope", not scope),
            ("requirements", not requirements),
            ("test_cases", not test_cases),
        ):
            if missing:
                unresolved.append(field)

        field_metadata = {
            field: self._field_metadata(getattr(extracted, field))
            for field in (
                "domain_key",
                "owner_name",
                "owner_employee_id",
                "execution_start_date",
                "execution_end_date",
                "scope",
            )
        }
        if catalog_item is not None:
            field_metadata["domain_name"] = FieldMetadata(
                provenance="derived",
                evidence_references=field_metadata["domain_key"].evidence_references,
            )
            field_metadata["domain_code"] = FieldMetadata(
                provenance="derived",
                evidence_references=field_metadata["domain_key"].evidence_references,
            )
        if start_derived:
            field_metadata["execution_start_date"] = FieldMetadata(
                provenance="derived", evidence_references=[]
            )
        if end_derived:
            field_metadata["execution_end_date"] = FieldMetadata(
                provenance="derived", evidence_references=[]
            )
        detail_references = self._deduplicate_references(
            [reference for item in requirements for reference in item.evidence_references]
            + [reference for item in test_cases for reference in item.evidence_references]
            + [
                reference
                for metadata in field_metadata.values()
                for reference in metadata.evidence_references
            ]
        )
        return TestPlanDetailContent(
            domain_key=domain_key,
            domain_name=domain_name,
            domain_code=domain_code,
            owner_name=owner_name,
            owner_employee_id=owner_employee_id,
            execution_start_date=start,
            execution_end_date=end,
            scope=scope,
            requirements=requirements,
            test_cases=test_cases,
            evidence_references=detail_references,
            unresolved_fields=list(dict.fromkeys(unresolved)),
            field_metadata=field_metadata,
        )

    def _field_metadata(self, value: object) -> FieldMetadata:
        evidence_ids = getattr(value, "evidence_ids", [])
        raw_value = getattr(value, "value", getattr(value, "values", []))
        has_value = bool(raw_value)
        references = self._references(evidence_ids)
        return FieldMetadata(
            provenance="source" if has_value and references else "unresolved",
            evidence_references=references,
        )

    def _trusted_text(
        self,
        value: object,
        label: str,
        questions: list[str],
    ) -> str:
        raw_value = getattr(value, "value", "")
        normalized = raw_value.strip() if isinstance(raw_value, str) else ""
        evidence_ids = getattr(value, "evidence_ids", [])
        if normalized and not self._references(evidence_ids):
            questions.append(f"{label}缺少合法邮件证据，已清空并等待人工确认。")
            return ""
        return normalized

    def _trusted_list(
        self,
        value: ExtractedList,
        label: str,
        questions: list[str],
    ) -> list[str]:
        cleaned = self._clean_list(value)
        if cleaned and not self._references(value.evidence_ids):
            questions.append(f"{label}缺少合法邮件证据，已清空并等待人工确认。")
            return []
        return cleaned

    def _references(self, temporary_ids: list[str]) -> list[EvidenceReference]:
        references = []
        for temporary_id in temporary_ids:
            segment = self.evidence.get(temporary_id)
            if segment is None:
                continue
            references.append(
                EvidenceReference(
                    evidence_segment_id=segment.id,
                    section_type=segment.section_type,
                    start_offset=segment.start_offset,
                    end_offset=segment.end_offset,
                    content_sha256=segment.content_sha256,
                )
            )
        return self._deduplicate_references(references)

    def _references_for_section(self, section_type: str) -> list[EvidenceReference]:
        ids = [key for key, value in self.evidence.items() if value.section_type == section_type]
        return self._references(ids)

    @staticmethod
    def _deduplicate_references(
        references: list[EvidenceReference],
    ) -> list[EvidenceReference]:
        unique: dict[str, EvidenceReference] = {}
        for reference in references:
            unique.setdefault(str(reference.evidence_segment_id), reference)
        return list(unique.values())

    @staticmethod
    def _clean_list(value: ExtractedList) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value.values if item.strip()))

    @staticmethod
    def _catalog_item(value: str, catalog: Catalog) -> CatalogItem | None:
        normalized = value.strip().casefold()
        if not normalized:
            return None
        for item in catalog.items:
            candidates = (item.key, item.display_name, item.platform_value, *item.aliases)
            if item.enabled and normalized in {candidate.casefold() for candidate in candidates}:
                return item
        return None

    def _catalog_value(self, value: str, catalog: Catalog) -> str:
        item = self._catalog_item(value, catalog)
        return item.key if item is not None else ""

    @staticmethod
    def _date_value(value: str, label: str, questions: list[str]) -> date | None:
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return date.fromisoformat(normalized)
        except ValueError:
            questions.append(f"请确认格式无效的{label}：{normalized}")
            return None


def _blank_extraction_payload() -> dict[str, object]:
    text: dict[str, object] = {"value": "", "evidence_ids": []}
    values: dict[str, object] = {"values": [], "evidence_ids": []}
    return {
        "plan_name": dict(text),
        "project_name": dict(text),
        "project_code": dict(text),
        "requirement_ids": dict(values),
        "test_type": dict(text),
        "test_stage": dict(text),
        "test_round": dict(text),
        "priority": dict(text),
        "test_version": dict(text),
        "planned_start_date": dict(text),
        "planned_end_date": dict(text),
        "objective": dict(text),
        "scope": dict(text),
        "environment": dict(text),
        "risks": dict(values),
        "dependencies": dict(values),
        "notes": dict(text),
        "open_questions": [],
        "details": [],
    }

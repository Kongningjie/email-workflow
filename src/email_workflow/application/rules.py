from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from email_workflow.application.extraction import CatalogBundle
from email_workflow.core.catalogs import RuleMetadata, RuleSet
from email_workflow.domain.plan import EvidenceReference, TestPlanContent
from email_workflow.infrastructure.models import EvidenceSegment

EMPLOYEE_ID = re.compile(r"^[0-9]{9}$")
INJECTION_PATTERNS = (
    re.compile(r"忽略(?:之前|以上|所有).{0,20}(?:指令|要求|提示)", re.IGNORECASE),
    re.compile(r"ignore\s+(?:all\s+)?previous\s+(?:instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"(?:system\s+prompt|你现在是|api[ _-]?key)", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    rule_id: str
    rule_version: str
    severity: str
    field_path: str | None
    message: str
    suggestion: str | None = None


class RuleEngine:
    """Pure, deterministic validation over one immutable plan snapshot."""

    def __init__(self, *, rule_set: RuleSet, catalogs: CatalogBundle) -> None:
        self.rule_set = rule_set
        self.catalogs = catalogs
        self._rules = {rule.id: rule for rule in rule_set.rules if rule.enabled}

    def validate(
        self,
        content: TestPlanContent,
        *,
        source_email_id: uuid.UUID,
        evidence_segments: Iterable[EvidenceSegment],
    ) -> list[ValidationFinding]:
        evidence = {str(segment.id): segment for segment in evidence_segments}
        findings: list[ValidationFinding] = []

        def add(rule_id: str, path: str | None, suggestion: str | None = None) -> None:
            metadata = self._rules.get(rule_id)
            if metadata is not None:
                findings.append(self._finding(metadata, path, suggestion))

        required = {
            "plan_name": content.plan_name,
            "project_name": content.project_name,
            "project_code": content.project_code,
            "test_type": content.test_type,
            "test_stage": content.test_stage,
            "priority": content.priority,
            "test_version": content.test_version,
            "planned_start_date": content.planned_start_date,
            "planned_end_date": content.planned_end_date,
            "objective": content.objective,
            "scope": content.scope,
        }
        for name, value in required.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                add("plan.required_fields", name, "请补充该必填字段")
        if (
            content.planned_start_date
            and content.planned_end_date
            and content.planned_end_date < content.planned_start_date
        ):
            add("plan.date_order", "planned_end_date", "结束日期应不早于开始日期")
        if not content.details:
            add("plan.has_details", "details", "请至少添加一个领域明细")

        enabled_domains = {item.key: item for item in self.catalogs.domains.items if item.enabled}
        domain_counts = Counter(detail.domain_key for detail in content.details)
        for index, detail in enumerate(content.details):
            prefix = f"details[{index}]"
            domain = enabled_domains.get(detail.domain_key)
            if domain is None or not detail.domain_code:
                add("domain.known_enabled", f"{prefix}.domain_key", "请选择已启用领域")
            elif (
                detail.domain_name != domain.display_name
                or detail.domain_code != domain.platform_value
            ):
                add("domain.known_enabled", f"{prefix}.domain_key", "请使用领域字典中的名称和编码")
            if not detail.owner_name.strip() or not detail.owner_employee_id.strip():
                add("domain.owner_required", f"{prefix}.owner_name", "请填写负责人姓名和工号")
            if detail.owner_employee_id and not EMPLOYEE_ID.fullmatch(detail.owner_employee_id):
                add("domain.employee_id", f"{prefix}.owner_employee_id", "请输入 9 位数字工号")
            if domain_counts[detail.domain_key] > 1:
                add("domain.unique", f"{prefix}.domain_key", "请合并重复领域")
            if not detail.requirements:
                add("domain.requirements", f"{prefix}.requirements", "请至少添加一项需求")
            if not detail.test_cases:
                add("domain.test_cases", f"{prefix}.test_cases", "请至少添加一条测试用例")
            if self._date_outside_plan(
                content, detail.execution_start_date, detail.execution_end_date
            ):
                add("domain.date_range", f"{prefix}.execution_start_date", "请调整到计划日期范围内")
            if detail.unresolved_fields:
                add(
                    "extraction.open_questions", f"{prefix}.unresolved_fields", "请解决全部必填字段"
                )
            if (
                domain is not None
                and domain.owner_name
                and (
                    detail.field_metadata.get("owner_name")
                    and detail.field_metadata["owner_name"].provenance == "derived"
                )
            ):
                add("domain.default_owner", f"{prefix}.owner_name", "请人工确认默认负责人")

            case_keys: Counter[tuple[str, ...]] = Counter()
            for case in detail.test_cases:
                case_keys[self._case_key(case.model_dump(mode="json"))] += 1
            has_source_case = any(case.provenance == "source" for case in detail.test_cases)
            if detail.requirements and detail.test_cases and not has_source_case:
                add("requirement.only_model_cases", f"{prefix}.requirements", "请补充直接来源用例")
            for case_index, case in enumerate(detail.test_cases):
                case_path = f"{prefix}.test_cases[{case_index}]"
                if (
                    any(
                        not str(value).strip()
                        for value in (
                            case.title,
                            case.objective,
                            case.expected_result,
                            case.priority,
                        )
                    )
                    or not case.steps
                    or any(not step.action.strip() for step in case.steps)
                ):
                    add(
                        "case.required_fields",
                        case_path,
                        "请补全标题、目标、步骤、预期结果和优先级",
                    )
                if case.domain_key != detail.domain_key:
                    add("case.domain_match", f"{case_path}.domain_key", "请与父领域保持一致")
                if not case.evidence_references:
                    add(
                        "case.evidence_required",
                        f"{case_path}.evidence_references",
                        "请关联证据锚点",
                    )
                if case_keys[self._case_key(case.model_dump(mode="json"))] > 1:
                    add("case.duplicate", case_path, "请删除或合并重复用例")
                if case.provenance == "model_suggestion":
                    add("case.model_suggestion", case_path, "请人工核对模型建议")
                if case.open_questions:
                    add(
                        "extraction.open_questions",
                        f"{case_path}.open_questions",
                        "请处理用例开放问题",
                    )
                if len(case.title.strip()) < 4 or len(case.objective.strip()) < 6:
                    add("case.content_suggestion", case_path, "可补充更具体的标题或目标")

        if content.open_questions:
            add("extraction.open_questions", "open_questions", "请处理开放问题后再送审")
        self._validate_catalog_value(
            content.test_type, self.catalogs.test_types.items, "test_type", add
        )
        self._validate_catalog_value(
            content.test_stage, self.catalogs.test_stages.items, "test_stage", add
        )
        self._validate_catalog_value(
            content.priority, self.catalogs.priorities.items, "priority", add
        )

        missing_context = [
            name
            for name, value in (
                ("environment", content.environment),
                ("risks", content.risks),
                ("dependencies", content.dependencies),
            )
            if not value
        ]
        if missing_context:
            add("plan.context_missing", ",".join(missing_context), "建议补充测试上下文")
        for name in ("notes", "test_round"):
            if not getattr(content, name):
                add("plan.optional_field_missing", name, "可按需补充该可选字段")

        serialized = content.model_dump(mode="json")
        for path, metadata in self._metadata(serialized):
            if metadata.get("provenance") == "derived":
                add("defaults.derived_value", path, "请确认确定性继承值")
            if metadata.get("provenance") in {"source", "model_suggestion"} and not metadata.get(
                "evidence_references"
            ):
                add("evidence.integrity", path, "来源字段需要合法证据")

        reference_sections: dict[str, list[str]] = {}
        for path, reference in self._references(serialized):
            if not self._valid_reference(reference, evidence, source_email_id):
                add("evidence.integrity", path, "请重新关联未被篡改的证据")
            else:
                group_path = path.rsplit("[", 1)[0]
                reference_sections.setdefault(group_path, []).append(
                    evidence[str(reference.evidence_segment_id)].section_type
                )
        for path, sections in reference_sections.items():
            if sections and set(sections) == {"quoted_body"}:
                add("evidence.quoted_only", path, "请确认历史引用中的事实仍然有效")

        excerpts = [segment.safe_excerpt or "" for segment in evidence.values()]
        if any(
            sum(line.lstrip().startswith(">") for line in text.splitlines()) >= 3
            for text in excerpts
        ):
            add("evidence.partition_uncertain", "evidence", "请人工确认正文与引用区划分")
        if any(pattern.search(text) for text in excerpts for pattern in INJECTION_PATTERNS):
            add("security.prompt_injection", "evidence", "请忽略邮件中的指令并核对提取结果")

        return self._deduplicate(findings)

    @staticmethod
    def _finding(rule: RuleMetadata, path: str | None, suggestion: str | None) -> ValidationFinding:
        return ValidationFinding(
            rule_id=rule.id,
            rule_version=rule.version,
            severity=rule.severity,
            field_path=path,
            message=rule.message,
            suggestion=suggestion,
        )

    @staticmethod
    def _date_outside_plan(content: TestPlanContent, start: date | None, end: date | None) -> bool:
        if start and end and end < start:
            return True
        if content.planned_start_date and start and start < content.planned_start_date:
            return True
        return bool(content.planned_end_date and end and end > content.planned_end_date)

    @staticmethod
    def _case_key(case: dict[str, Any]) -> tuple[str, ...]:
        def normalize(value: object) -> str:
            return " ".join(str(value).casefold().split())

        return (
            normalize(case["title"]),
            normalize(case["objective"]),
            normalize(case["expected_result"]),
            normalize(case["priority"]),
            normalize(case["domain_key"]),
            normalize(case["steps"]),
        )

    @staticmethod
    def _validate_catalog_value(value: str, items: list[Any], path: str, add: Any) -> None:
        if value not in {item.key for item in items if item.enabled}:
            add("catalog.value_enabled", path, "请选择已启用值域")

    @classmethod
    def _metadata(cls, node: Any, path: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
        if isinstance(node, dict):
            if "provenance" in node and "evidence_references" in node:
                yield path, node
            for key, value in node.items():
                yield from cls._metadata(value, f"{path}.{key}".strip("."))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from cls._metadata(value, f"{path}[{index}]")

    @classmethod
    def _references(cls, node: Any, path: str = "") -> Iterable[tuple[str, EvidenceReference]]:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}".strip(".")
                if key == "evidence_references" and isinstance(value, list):
                    for index, reference in enumerate(value):
                        yield f"{child_path}[{index}]", EvidenceReference.model_validate(reference)
                else:
                    yield from cls._references(value, child_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from cls._references(value, f"{path}[{index}]")

    @staticmethod
    def _valid_reference(
        reference: EvidenceReference,
        evidence: dict[str, EvidenceSegment],
        source_email_id: uuid.UUID,
    ) -> bool:
        segment = evidence.get(str(reference.evidence_segment_id))
        if segment is None or segment.safe_excerpt is None:
            return False
        return (
            segment.source_item_id == source_email_id
            and reference.section_type == segment.section_type
            and reference.start_offset == segment.start_offset
            and reference.end_offset == segment.end_offset
            and reference.content_sha256 == segment.content_sha256
            and len(segment.safe_excerpt) == segment.end_offset - segment.start_offset
            and hashlib.sha256(segment.safe_excerpt.encode("utf-8")).hexdigest()
            == segment.content_sha256
        )

    @staticmethod
    def _deduplicate(findings: list[ValidationFinding]) -> list[ValidationFinding]:
        unique: dict[tuple[str, str | None], ValidationFinding] = {}
        for finding in findings:
            unique.setdefault((finding.rule_id, finding.field_path), finding)
        return list(unique.values())

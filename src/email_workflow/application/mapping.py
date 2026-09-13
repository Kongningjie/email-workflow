from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from email_workflow.application.extraction import CatalogBundle
from email_workflow.core.canonical import canonical_sha256
from email_workflow.core.catalogs import MappingDocument
from email_workflow.domain.plan import TestPlanContent
from email_workflow.domain.platform import (
    PlatformDomain,
    PlatformPlanPayload,
    PlatformStep,
    PlatformTestCase,
)


class PayloadMappingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PayloadLimitFinding:
    field_path: str
    message: str
    near_limit: bool


class PlatformPayloadMapper:
    def __init__(self, *, mapping: MappingDocument, catalogs: CatalogBundle) -> None:
        self.mapping = mapping
        self.catalogs = catalogs

    def map(
        self, *, plan_id: uuid.UUID, version_number: int, content: TestPlanContent
    ) -> PlatformPlanPayload:
        if content.planned_start_date is None or content.planned_end_date is None:
            raise PayloadMappingError("计划日期不完整")
        test_types = self._platform_values(self.catalogs.test_types.items)
        test_stages = self._platform_values(self.catalogs.test_stages.items)
        priorities = self._platform_values(self.catalogs.priorities.items)
        try:
            domains = [
                PlatformDomain(
                    domain_code=detail.domain_code,
                    owner_name=detail.owner_name,
                    owner_employee_id=detail.owner_employee_id,
                    execution_start_date=detail.execution_start_date,
                    execution_end_date=detail.execution_end_date,
                    scope=detail.scope,
                    requirements=[item.text for item in detail.requirements],
                    test_cases=[
                        PlatformTestCase(
                            title=case.title,
                            objective=case.objective,
                            preconditions=case.preconditions,
                            steps=[
                                PlatformStep(step_number=step.step_number, action=step.action)
                                for step in case.steps
                            ],
                            test_data=case.test_data,
                            expected_result=case.expected_result,
                            priority=priorities[case.priority],
                        )
                        for case in detail.test_cases
                    ],
                )
                for detail in content.details
            ]
            return PlatformPlanPayload(
                contract_version=self.mapping.contract_version,
                source_system=self.mapping.fixed_values["source_system"],
                internal_plan_id=plan_id,
                internal_version=version_number,
                plan_name=content.plan_name,
                project_name=content.project_name,
                project_code=content.project_code,
                requirement_ids=content.requirement_ids,
                test_type=test_types[content.test_type],
                test_stage=test_stages[content.test_stage],
                test_round=content.test_round,
                priority=priorities[content.priority],
                test_version=content.test_version,
                planned_start_date=content.planned_start_date,
                planned_end_date=content.planned_end_date,
                objective=content.objective,
                scope=content.scope,
                environment=content.environment,
                risks=content.risks,
                dependencies=content.dependencies,
                domains=domains,
            )
        except (KeyError, ValueError) as exc:
            raise PayloadMappingError("计划内容无法映射到平台值域") from exc

    def inspect_limits(self, content: TestPlanContent) -> list[PayloadLimitFinding]:
        fields: list[tuple[str, str, str]] = [
            ("plan_name", content.plan_name, "plan_name"),
            ("project_name", content.project_name, "project_name"),
            ("project_code", content.project_code, "project_code"),
            ("test_round", content.test_round, "test_round"),
            ("test_version", content.test_version, "test_version"),
            ("objective", content.objective, "objective"),
            ("scope", content.scope, "scope"),
            ("environment", content.environment, "environment"),
        ]
        for domain_index, detail in enumerate(content.details):
            fields.append((f"details[{domain_index}].scope", detail.scope, "domain_scope"))
            fields.extend(
                (f"details[{domain_index}].requirements[{index}]", item.text, "requirement")
                for index, item in enumerate(detail.requirements)
            )
            for case_index, case in enumerate(detail.test_cases):
                prefix = f"details[{domain_index}].test_cases[{case_index}]"
                fields.extend(
                    (
                        (f"{prefix}.title", case.title, "case_title"),
                        (f"{prefix}.objective", case.objective, "case_objective"),
                        (
                            f"{prefix}.expected_result",
                            case.expected_result,
                            "case_expected_result",
                        ),
                    )
                )
                fields.extend(
                    (f"{prefix}.steps[{index}].action", step.action, "case_step")
                    for index, step in enumerate(case.steps)
                )
        findings: list[PayloadLimitFinding] = []
        for path, value, limit_name in fields:
            self._append_limit_finding(findings, path, len(value), limit_name, "字段长度")
        case_count = sum(len(detail.test_cases) for detail in content.details)
        self._append_limit_finding(
            findings, "details", len(content.details), "max_domains", "条目数量"
        )
        self._append_limit_finding(
            findings, "details[].test_cases", case_count, "max_cases_total", "条目总数"
        )
        for domain_index, detail in enumerate(content.details):
            self._append_limit_finding(
                findings,
                f"details[{domain_index}].test_cases",
                len(detail.test_cases),
                "max_cases_per_domain",
                "条目数量",
            )
            for case_index, case in enumerate(detail.test_cases):
                self._append_limit_finding(
                    findings,
                    f"details[{domain_index}].test_cases[{case_index}].steps",
                    len(case.steps),
                    "max_steps_per_case",
                    "条目数量",
                )
        return findings

    def _append_limit_finding(
        self,
        findings: list[PayloadLimitFinding],
        path: str,
        actual: int,
        limit_name: str,
        measurement: str,
    ) -> None:
        limit = self.mapping.limits[limit_name]
        if actual > limit:
            findings.append(
                PayloadLimitFinding(path, f"{measurement}超过平台上限 {limit}", False)
            )
        elif actual >= int(limit * self.mapping.near_limit_ratio):
            findings.append(
                PayloadLimitFinding(path, f"{measurement}接近平台上限 {limit}", True)
            )

    @staticmethod
    def _platform_values(items: list[Any]) -> dict[str, str]:
        return {item.key: item.platform_value for item in items if item.enabled}


def submission_idempotency_key(
    *, plan_id: uuid.UUID, version_number: int, payload: PlatformPlanPayload
) -> str:
    return canonical_sha256(
        {
            "plan_id": str(plan_id),
            "version_number": version_number,
            "payload_sha256": canonical_sha256(payload.model_dump(mode="json", by_alias=True)),
        }
    )

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from email_workflow.application.evidence import EvidenceSegmenter
from email_workflow.application.extraction import (
    CatalogBundle,
    ExtractionFailure,
    ExtractionValidator,
)
from email_workflow.core.catalogs import Catalog, load_catalog, load_prompt_document
from email_workflow.core.config import Settings
from email_workflow.domain.plan import (
    ExtractedList,
    ExtractedText,
    ExtractionEvidence,
    ExtractionPayload,
    ExtractionRequest,
)
from email_workflow.infrastructure.email_parser import SafeEmailParser
from email_workflow.infrastructure.llm import LLMExtractor

pytestmark = pytest.mark.live_llm


@dataclass(frozen=True, slots=True)
class ExpectedResult:
    fixture: str
    facts: dict[str, str]
    domains: frozenset[str]


EXPECTED_RESULTS = (
    ExpectedResult(
        "01-plain-single-domain.eml",
        {
            "project_name": "Orion",
            "project_code": "ORION-R2",
            "requirement_ids": "REQ-1001",
            "test_type": "functional",
            "test_stage": "system",
            "priority": "high",
            "test_version": "R2",
            "planned_start_date": "2026-09-15",
            "planned_end_date": "2026-09-18",
            "domain.communication.owner_name": "李明",
            "domain.communication.owner_employee_id": "000123456",
        },
        frozenset({"communication"}),
    ),
    ExpectedResult(
        "02-html-multi-domain-table.eml",
        {
            "project_name": "Nova",
            "project_code": "NOVA-7",
            "test_stage": "acceptance",
            "test_version": "7.0",
            "planned_start_date": "2026-09-20",
            "planned_end_date": "2026-09-25",
            "domain.communication.owner_name": "王芳",
            "domain.communication.owner_employee_id": "000234567",
            "domain.power.owner_name": "赵青",
            "domain.power.owner_employee_id": "000345678",
        },
        frozenset({"communication", "power"}),
    ),
    ExpectedResult(
        "03-quoted-history.eml",
        {
            "project_name": "Atlas",
            "project_code": "ATLAS-3",
            "test_type": "stability",
            "test_stage": "system",
            "test_version": "3.4",
            "planned_start_date": "2026-09-21",
            "planned_end_date": "2026-09-24",
            "domain.stability.owner_name": "陈宇",
            "domain.stability.owner_employee_id": "000456789",
        },
        frozenset({"stability"}),
    ),
    ExpectedResult(
        "04-missing-required-facts.eml",
        {"project_name": "Vega"},
        frozenset({"power"}),
    ),
    ExpectedResult(
        "05-prompt-injection.eml",
        {"project_code": "SEC-5"},
        frozenset({"communication"}),
    ),
    ExpectedResult(
        "06-duplicate-domain-cases.eml",
        {
            "project_name": "Helios",
            "test_type": "regression",
            "domain.communication.owner_name": "周林",
            "domain.communication.owner_employee_id": "000567890",
        },
        frozenset({"communication"}),
    ),
    ExpectedResult(
        "07-unknown-domain-ambiguous.eml",
        {"project_name": "Lyra"},
        frozenset(),
    ),
    ExpectedResult(
        "08-near-generation-limit.eml",
        {
            "project_name": "Polaris",
            "project_code": "POLARIS-9",
            "test_type": "regression",
            "test_stage": "system",
            "test_version": "9.1",
            "planned_start_date": "2026-09-26",
            "planned_end_date": "2026-09-30",
            "domain.communication.owner_name": "林澈",
            "domain.communication.owner_employee_id": "000678901",
        },
        frozenset({"communication"}),
    ),
)

MONITORED_TOP_LEVEL_FIELDS = (
    "project_name",
    "project_code",
    "requirement_ids",
    "test_type",
    "test_stage",
    "priority",
    "test_version",
    "planned_start_date",
    "planned_end_date",
)


def _catalogs() -> CatalogBundle:
    config = Path("config")
    return CatalogBundle(
        domains=load_catalog(config / "domains/v1.yaml"),
        test_types=load_catalog(config / "values/test-types-v1.yaml"),
        test_stages=load_catalog(config / "values/test-stages-v1.yaml"),
        priorities=load_catalog(config / "values/priorities-v1.yaml"),
    )


def _catalog_key(value: str, catalog: Catalog) -> str:
    normalized = value.strip().casefold()
    for item in catalog.items:
        candidates = (item.key, item.display_name, item.platform_value, *item.aliases)
        if normalized in {candidate.casefold() for candidate in candidates}:
            return item.key
    return value.strip()


def _request(fixture: str, catalogs: CatalogBundle) -> ExtractionRequest:
    parser = SafeEmailParser(
        max_body_chars=200_000,
        max_header_count=200,
        max_header_value_chars=16_384,
        max_mime_depth=10,
        max_mime_parts=100,
    )
    parsed = parser.parse((Path("tests/fixtures/eml") / fixture).read_bytes())
    drafts = EvidenceSegmenter(segment_chars=1_000, overlap_chars=100).segment(parsed)
    return ExtractionRequest(
        evidence=[
            ExtractionEvidence(
                evidence_id=f"evidence-{index + 1:04d}",
                section_type=draft.section_type.value,
                text=draft.text,
            )
            for index, draft in enumerate(drafts)
        ],
        **catalogs.extraction_request_catalogs(),
    )


def _flatten(
    payload: ExtractionPayload, catalogs: CatalogBundle
) -> tuple[dict[str, str], set[str]]:
    facts: dict[str, str] = {}
    for field in MONITORED_TOP_LEVEL_FIELDS:
        extracted = cast(ExtractedList | ExtractedText, getattr(payload, field))
        value = (
            ",".join(extracted.values)
            if isinstance(extracted, ExtractedList)
            else extracted.value
        )
        if field == "test_type":
            value = _catalog_key(value, catalogs.test_types)
        elif field == "test_stage":
            value = _catalog_key(value, catalogs.test_stages)
        elif field == "priority":
            value = _catalog_key(value, catalogs.priorities)
        if value.strip():
            facts[field] = value.strip()

    domains: set[str] = set()
    for detail in payload.details:
        domain_key = _catalog_key(detail.domain_key.value, catalogs.domains)
        if not domain_key:
            continue
        domains.add(domain_key)
        if detail.owner_name.value.strip():
            facts[f"domain.{domain_key}.owner_name"] = detail.owner_name.value.strip()
        if detail.owner_employee_id.value.strip():
            facts[f"domain.{domain_key}.owner_employee_id"] = (
                detail.owner_employee_id.value.strip()
            )
    return facts, domains


def _normalized(field: str, value: str) -> str:
    normalized = re.sub(r"[\s：:，,。.]", "", value).casefold()  # noqa: RUF001
    if field == "project_name":
        normalized = re.sub(r"^项目", "", normalized)
        normalized = re.sub(r"项目$", "", normalized)
    return normalized


def _case_summary(payload: ExtractionPayload, catalogs: CatalogBundle) -> list[dict[str, object]]:
    return [
        {
            "domain": _catalog_key(detail.domain_key.value, catalogs.domains),
            "cases": [
                {
                    "title": case.title.value,
                    "objective": case.objective.value,
                    "provenance": case.provenance,
                    "steps": len(case.steps),
                }
                for case in detail.test_cases
            ],
            "unresolved_fields": detail.unresolved_fields,
        }
        for detail in payload.details
    ]


@pytest.mark.asyncio
async def test_eight_golden_emails_meet_live_llm_metrics() -> None:
    settings = Settings()
    if not settings.run_live_llm_tests:
        pytest.skip("仅在 RUN_LIVE_LLM_TESTS=1 时运行真实模型测试")
    if settings.dashscope_api_key is None:
        pytest.skip("未配置 DASHSCOPE_API_KEY")
    api_key = settings.dashscope_api_key.get_secret_value()

    catalogs = _catalogs()
    prompt = load_prompt_document(Path("config/prompts/extraction-v1.yaml"))
    assert settings.dashscope_model == prompt.model
    extractor = LLMExtractor(
        api_key=api_key,
        base_url=settings.dashscope_base_url,
        model=settings.dashscope_model,
        timeout_seconds=settings.llm_timeout_seconds,
        prompt=prompt,
    )
    selected_fixtures = {
        item.strip()
        for item in os.getenv("LIVE_LLM_FIXTURES", "").split(",")
        if item.strip()
    }
    expected_results = tuple(
        item
        for item in EXPECTED_RESULTS
        if not selected_fixtures or item.fixture in selected_fixtures
    )
    assert expected_results, "LIVE_LLM_FIXTURES 未匹配任何黄金样例"
    expected_domain_count = sum(len(item.domains) for item in expected_results)
    recalled_domains = 0
    expected_fact_count = sum(len(item.facts) for item in expected_results)
    correct_facts = 0
    fabrications: list[str] = []
    summaries: list[dict[str, object]] = []

    for expected in expected_results:
        request = _request(expected.fixture, catalogs)
        try:
            payload = await extractor.extract(request)
            ExtractionValidator.validate_evidence_ids(
                payload, {item.evidence_id for item in request.evidence}
            )
        except ExtractionFailure as exc:
            summaries.append({"fixture": expected.fixture, "failure": exc.code})
            continue

        actual_facts, actual_domains = _flatten(payload, catalogs)
        recalled_domains += len(expected.domains & actual_domains)
        matches = 0
        for field, expected_value in expected.facts.items():
            actual_value = actual_facts.get(field, "")
            if _normalized(field, actual_value) == _normalized(field, expected_value):
                correct_facts += 1
                matches += 1
            elif actual_value:
                fabrications.append(f"{expected.fixture}:{field}")
        for field, actual_value in actual_facts.items():
            if field not in expected.facts and actual_value:
                fabrications.append(f"{expected.fixture}:{field}")
        for domain in actual_domains - expected.domains:
            fabrications.append(f"{expected.fixture}:domain.{domain}")
        summaries.append(
            {
                "fixture": expected.fixture,
                "domains": sorted(actual_domains),
                "fact_matches": matches,
                "fact_total": len(expected.facts),
                "actual_facts": actual_facts,
                "open_questions": payload.open_questions,
                "case_review": _case_summary(payload, catalogs),
            }
        )

    domain_recall = recalled_domains / expected_domain_count if expected_domain_count else 1.0
    fact_accuracy = correct_facts / expected_fact_count
    report = {
        "model": extractor.model,
        "prompt_version": prompt.version,
        "domain_recall": domain_recall,
        "fact_accuracy": fact_accuracy,
        "fabrication_count": len(fabrications),
        "fabrication_fields": fabrications,
        "samples": summaries,
    }
    print("\nPHASE6_LIVE_EVALUATION=" + json.dumps(report, ensure_ascii=False))

    if not selected_fixtures:
        assert domain_recall >= 0.90
        assert fact_accuracy >= 0.95
        assert fabrications == []

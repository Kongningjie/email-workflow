from __future__ import annotations

import hashlib
import logging
import uuid

import jcs  # type: ignore[import-untyped]
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_workflow.application.extraction import (
    CatalogBundle,
    EvidenceRebuilder,
    ExtractionFailure,
    ExtractionValidator,
    StructuredRequirementExtractor,
    TestPlanDraftBuilder,
)
from email_workflow.core.catalogs import PromptDocument
from email_workflow.domain.plan import ExtractionEvidence, ExtractionRequest, TestPlanContent
from email_workflow.infrastructure.import_repository import ImportRepository
from email_workflow.infrastructure.models import (
    EvidenceSegment,
    ImportedEmail,
    TestPlan,
    TestPlanVersion,
)
from email_workflow.infrastructure.plan_repository import PlanRepository

logger = logging.getLogger(__name__)


class PlanGenerationService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        extractor: StructuredRequirementExtractor,
        catalogs: CatalogBundle,
        prompt: PromptDocument,
        evidence_rebuilder: EvidenceRebuilder,
    ) -> None:
        expected_limits = {
            "max_domains": 10,
            "max_cases_per_domain": 20,
            "max_cases_total": 100,
            "max_steps_per_case": 20,
        }
        if prompt.limits.model_dump() != expected_limits:
            raise ValueError("Prompt 生成规模必须与结构化提取 Schema 一致")
        _ = catalogs.value_version
        self.session_factory = session_factory
        self.extractor = extractor
        self.catalogs = catalogs
        self.prompt = prompt
        self.evidence_rebuilder = evidence_rebuilder

    async def generate(self, import_id: uuid.UUID) -> uuid.UUID:
        imported, evidence, existing_plan_id = await self._prepare(import_id)
        if existing_plan_id is not None:
            return existing_plan_id

        temporary_evidence = {
            f"evidence-{index + 1:04d}": segment for index, segment in enumerate(evidence)
        }
        builder = TestPlanDraftBuilder(
            catalogs=self.catalogs,
            evidence_by_temporary_id=temporary_evidence,
            email_subject=imported.subject,
        )
        failure_code: str | None = None
        try:
            self.evidence_rebuilder.validate(imported, evidence)
            request = self._request(temporary_evidence)
            extracted = await self.extractor.extract(request)
            ExtractionValidator.validate_evidence_ids(extracted, set(temporary_evidence))
            content = builder.build(extracted)
        except ExtractionFailure as exc:
            failure_code = exc.code
            logger.warning(
                "结构化提取工作流降级为空白草稿",
                extra={"result_status": failure_code},
            )
            content = builder.blank(failure_code)
        except (ValidationError, ValueError, TypeError, OSError):
            failure_code = "workflow_validation_failed"
            logger.warning(
                "结构化提取工作流校验失败",
                extra={"result_status": failure_code},
            )
            content = builder.blank(failure_code)
        except Exception:
            failure_code = "extractor_exception"
            logger.error(
                "结构化提取器发生未分类异常",
                extra={"result_status": failure_code},
            )
            content = builder.blank(failure_code)
        return await self._persist(imported.id, content, failure_code)

    async def _prepare(
        self, import_id: uuid.UUID
    ) -> tuple[ImportedEmail, list[EvidenceSegment], uuid.UUID | None]:
        async with self.session_factory() as session:
            imported = await ImportRepository(session).get(import_id)
            if imported is None or imported.parse_status != "parsed":
                raise ValueError("只有解析成功的邮件可以生成计划")
            plan = await PlanRepository(session).find_by_source_email(import_id)
            if plan is not None:
                return imported, [], plan.id
            evidence = await ImportRepository(session).evidence_for_import(import_id)
            imported.extraction_status = "extracting"
            await session.commit()
            return imported, evidence, None

    def _request(self, evidence_by_id: dict[str, EvidenceSegment]) -> ExtractionRequest:
        items = []
        for temporary_id, segment in evidence_by_id.items():
            if segment.safe_excerpt is None:
                raise ExtractionFailure("evidence_unavailable")
            items.append(
                ExtractionEvidence(
                    evidence_id=temporary_id,
                    section_type=segment.section_type,
                    text=segment.safe_excerpt,
                )
            )
        return ExtractionRequest(
            evidence=items,
            **self.catalogs.extraction_request_catalogs(),
        )

    async def _persist(
        self,
        import_id: uuid.UUID,
        content: TestPlanContent,
        failure_code: str | None,
    ) -> uuid.UUID:
        serialized = content.model_dump(mode="json")
        content_sha256 = hashlib.sha256(jcs.canonicalize(serialized)).hexdigest()
        prompt_sha256 = hashlib.sha256(self.prompt.system_prompt.encode("utf-8")).hexdigest()
        async with self.session_factory() as session:
            plan_repository = PlanRepository(session)
            existing = await plan_repository.find_by_source_email(import_id)
            if existing is not None:
                return existing.id
            imported = await ImportRepository(session).get(import_id)
            if imported is None:
                raise ValueError("导入记录不存在")
            plan_id = uuid.uuid4()
            plan = TestPlan(
                id=plan_id,
                source_email_id=import_id,
                current_version=1,
                status="draft",
                external_platform_id=None,
            )
            version = TestPlanVersion(
                id=uuid.uuid4(),
                test_plan_id=plan_id,
                version_number=1,
                content=serialized,
                content_sha256=content_sha256,
                domain_catalog_version=self.catalogs.domains.version,
                value_catalog_version=self.catalogs.value_version,
                prompt_version=self.prompt.version,
                prompt_sha256=prompt_sha256,
            )
            plan_repository.add(plan, version)
            imported.extraction_status = "extraction_failed" if failure_code else "extracted"
            imported.safe_error_summary = (
                f"extraction_{failure_code}" if failure_code is not None else None
            )
            await session.commit()
            return plan_id

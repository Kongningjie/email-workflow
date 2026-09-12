from __future__ import annotations

import os
from pathlib import Path

import pytest

from email_workflow.application.extraction import ExtractionValidator
from email_workflow.core.catalogs import load_prompt_document
from email_workflow.domain.plan import ExtractionEvidence, ExtractionRequest
from email_workflow.infrastructure.llm import LLMExtractor

pytestmark = pytest.mark.live_llm


@pytest.mark.asyncio
async def test_dashscope_live_structured_extraction() -> None:
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("仅在 RUN_LIVE_LLM_TESTS=1 时运行真实模型测试")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        pytest.skip("未配置 DASHSCOPE_API_KEY")

    prompt = load_prompt_document(Path("config/prompts/extraction-v1.yaml"))
    request = ExtractionRequest(
        evidence=[
            ExtractionEvidence(
                evidence_id="evidence-0001",
                section_type="current_body",
                text=(
                    "项目 Atlas, 编码 ATLAS-1, 需要进行通信功能系统测试。"
                    "负责人王芳, 工号 001234567, 计划日期 2026-09-15 至 2026-09-20。"
                    "验证设备断网后能够自动重连。"
                ),
            )
        ],
        allowed_domains={"communication": ["通信", "通信测试"]},
        allowed_test_types={"functional": ["功能", "功能测试"]},
        allowed_test_stages={"system": ["系统", "系统测试"]},
        allowed_priorities={"high": ["高", "P1"]},
    )
    result = await LLMExtractor(
        api_key=api_key,
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        model=os.getenv("DASHSCOPE_MODEL", prompt.model),
        timeout_seconds=60,
        prompt=prompt,
    ).extract(request)

    ExtractionValidator.validate_evidence_ids(result, {"evidence-0001"})
    assert len(result.details) <= prompt.limits.max_domains
    assert sum(len(detail.test_cases) for detail in result.details) <= 100

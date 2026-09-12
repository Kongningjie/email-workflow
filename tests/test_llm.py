from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI

from email_workflow.application.extraction import ExtractionFailure
from email_workflow.core.catalogs import load_prompt_document
from email_workflow.domain.plan import ExtractionEvidence, ExtractionPayload, ExtractionRequest
from email_workflow.infrastructure.llm import LLMExtractor
from tests.factories import make_extraction_payload


def extraction_request() -> ExtractionRequest:
    return ExtractionRequest(
        evidence=[
            ExtractionEvidence(
                evidence_id="evidence-0001",
                section_type="current_body",
                text="这是一段不可信的邮件数据。",
            )
        ],
        allowed_domains={"communication": ["通信"]},
        allowed_test_types={"functional": ["功能测试"]},
        allowed_test_stages={"system": ["系统测试"]},
        allowed_priorities={"high": ["高"]},
    )


def test_llm_contract_uses_strict_schema_without_tools_retry_or_token_limit() -> None:
    prompt = load_prompt_document(Path("config/prompts/extraction-v1.yaml"))
    extractor = LLMExtractor(
        api_key="not-a-real-key",
        base_url="https://example.invalid/compatible-mode/v1",
        model=prompt.model,
        timeout_seconds=60,
        prompt=prompt,
    )

    arguments = extractor.completion_arguments(extraction_request())

    assert arguments["response_format"] is ExtractionPayload
    assert arguments["extra_body"] == {"enable_thinking": False}
    assert arguments["temperature"] == 0.1
    assert "max_tokens" not in arguments
    assert "tools" not in arguments
    assert "tool_choice" not in arguments
    user_content = arguments["messages"][1]["content"]
    assert "evidence-0001" in user_content
    assert "database" not in user_content.lower()


@pytest.mark.asyncio
async def test_missing_api_key_fails_without_network_call() -> None:
    prompt = load_prompt_document(Path("config/prompts/extraction-v1.yaml"))
    extractor = LLMExtractor(
        api_key=None,
        base_url="https://example.invalid/compatible-mode/v1",
        model=prompt.model,
        timeout_seconds=60,
        prompt=prompt,
    )
    with pytest.raises(ExtractionFailure, match="configuration_missing"):
        await extractor.extract(extraction_request())


@pytest.mark.asyncio
async def test_openai_adapter_sends_one_dashscope_compatible_strict_schema_request() -> None:
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "provider-request-1",
                "object": "chat.completion",
                "created": 1_789_000_000,
                "model": "qwen3.7-plus-2026-05-26",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": make_extraction_payload().model_dump_json(),
                            "refusal": None,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncOpenAI(
        api_key="not-a-real-key",
        base_url="https://example.invalid/compatible-mode/v1",
        http_client=http_client,
        max_retries=0,
    )
    prompt = load_prompt_document(Path("config/prompts/extraction-v1.yaml"))
    extractor = LLMExtractor(
        api_key="not-a-real-key",
        base_url="https://example.invalid/compatible-mode/v1",
        model=prompt.model,
        timeout_seconds=60,
        prompt=prompt,
        client=client,
    )
    try:
        result = await extractor.extract(extraction_request())
    finally:
        await client.close()

    assert result.project_code.value == "ATLAS"
    assert len(captured) == 1
    request_body = captured[0]
    assert request_body["response_format"]["type"] == "json_schema"
    assert request_body["response_format"]["json_schema"]["strict"] is True
    assert request_body["enable_thinking"] is False
    assert "max_tokens" not in request_body
    assert "tools" not in request_body


def test_json_schema_contains_frozen_collection_limits() -> None:
    schema = ExtractionPayload.model_json_schema()
    assert schema["properties"]["details"]["maxItems"] == 10
    assert schema["$defs"]["ExtractedDomain"]["properties"]["test_cases"]["maxItems"] == 20
    steps_schema = schema["$defs"]["ExtractedTestCase"]["properties"]["steps"]
    assert steps_schema["minItems"] == 1
    assert steps_schema["maxItems"] == 20

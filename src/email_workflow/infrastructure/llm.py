from __future__ import annotations

import json
import logging
import time
from typing import Any, Never, cast

from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError, RateLimitError
from pydantic import ValidationError

from email_workflow.application.extraction import ExtractionFailure
from email_workflow.core.catalogs import PromptDocument
from email_workflow.domain.plan import ExtractionPayload, ExtractionRequest

logger = logging.getLogger(__name__)


class LLMExtractor:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout_seconds: int,
        prompt: PromptDocument,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.prompt = prompt
        self.client = client

    async def extract(self, request: ExtractionRequest) -> ExtractionPayload:
        if not self.api_key:
            self._log_result("configuration_missing", 0)
            raise ExtractionFailure("configuration_missing")
        owns_client = self.client is None
        client = self.client or AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=float(self.timeout_seconds),
            max_retries=0,
        )
        started_at = time.monotonic()
        try:
            completion = await client.beta.chat.completions.parse(
                **self.completion_arguments(request)
            )
            choice = completion.choices[0] if completion.choices else None
            if choice is None or choice.message.refusal:
                raise ExtractionFailure("model_refusal")
            parsed = choice.message.parsed
            if parsed is None:
                raise ExtractionFailure("invalid_structured_output")
            duration_ms = round((time.monotonic() - started_at) * 1_000)
            usage = completion.usage
            self._log_result(
                "succeeded",
                duration_ms,
                provider_request_id=completion.id,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
            )
            return cast(ExtractionPayload, parsed)
        except ExtractionFailure as exc:
            self._log_result(exc.code, round((time.monotonic() - started_at) * 1_000))
            raise
        except APITimeoutError as exc:
            self._raise_failure("timeout", started_at, exc)
        except RateLimitError as exc:
            self._raise_failure("rate_limited", started_at, exc)
        except APIStatusError as exc:
            self._raise_failure(f"provider_http_{exc.status_code}", started_at, exc)
        except (OpenAIError, ValidationError, ValueError, TypeError) as exc:
            self._raise_failure("invalid_structured_output", started_at, exc)
        finally:
            if owns_client:
                await client.close()

    def completion_arguments(self, request: ExtractionRequest) -> dict[str, Any]:
        valid_evidence_ids = [item.evidence_id for item in request.evidence]
        user_payload = {
            "valid_evidence_ids": valid_evidence_ids,
            "extraction_request": request.model_dump(mode="json"),
        }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.prompt.system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "response_format": ExtractionPayload,
            "temperature": self.prompt.temperature,
            "extra_body": {"enable_thinking": self.prompt.thinking},
        }

    def _raise_failure(self, code: str, started_at: float, cause: Exception) -> Never:
        self._log_result(code, round((time.monotonic() - started_at) * 1_000))
        raise ExtractionFailure(code) from cause

    def _log_result(
        self,
        result_status: str,
        duration_ms: int,
        *,
        provider_request_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        extra: dict[str, str | int] = {
            "llm_model": self.model,
            "duration_ms": duration_ms,
            "result_status": result_status,
        }
        if provider_request_id:
            extra["provider_request_id"] = provider_request_id
        if prompt_tokens is not None:
            extra["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            extra["completion_tokens"] = completion_tokens
        logger.info("结构化提取调用完成", extra=extra)

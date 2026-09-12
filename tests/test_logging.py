import json
import logging
from typing import Any

from email_workflow.core.logging import JsonFormatter, configure_logging


def test_json_formatter_emits_only_allowlisted_context() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="safe event",
        args=(),
        exc_info=None,
    )
    record.__dict__["request_id"] = "request-123"
    record.__dict__["email_body"] = "不得进入日志的正文"

    payload: dict[str, Any] = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "safe event"
    assert payload["request_id"] == "request-123"
    assert "email_body" not in payload


def test_configure_logging_disables_url_access_log() -> None:
    configure_logging("INFO")

    access_logger = logging.getLogger("uvicorn.access")
    assert access_logger.disabled is True
    assert access_logger.handlers == []

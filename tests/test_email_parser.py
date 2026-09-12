from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from email_workflow.domain.email import ParseWarningCode
from email_workflow.infrastructure.email_parser import EmailParseError, SafeEmailParser


@pytest.fixture
def parser() -> SafeEmailParser:
    return SafeEmailParser(
        max_body_chars=200_000,
        max_header_count=200,
        max_header_value_chars=16_384,
        max_mime_depth=10,
        max_mime_parts=100,
    )


def test_all_golden_emails_have_safe_text_body(parser: SafeEmailParser) -> None:
    fixtures = sorted(Path("tests/fixtures/eml").glob("*.eml"))
    assert len(fixtures) == 8
    for fixture in fixtures:
        parsed = parser.parse(fixture.read_bytes())
        assert parsed.current_body or parsed.quoted_body
        assert len(parsed.current_body) + len(parsed.quoted_body) <= 200_000


def test_html_removes_active_content_and_remote_resources(parser: SafeEmailParser) -> None:
    raw = Path("tests/fixtures/eml/02-html-multi-domain-table.eml").read_bytes()
    parsed = parser.parse(raw)

    assert "Nova 验收测试" in parsed.current_body
    assert "tracker.invalid" not in parsed.current_body
    assert "alert" not in parsed.current_body
    assert ParseWarningCode.ACTIVE_CONTENT_REMOVED in parsed.warnings
    assert ParseWarningCode.REMOTE_RESOURCE_REMOVED in parsed.warnings


def test_quote_history_is_separated(parser: SafeEmailParser) -> None:
    raw = Path("tests/fixtures/eml/03-quoted-history.eml").read_bytes()
    parsed = parser.parse(raw)

    assert "连续运行 72 小时" in parsed.current_body
    assert "项目 Atlas" in parsed.quoted_body
    assert "Original Message" in parsed.quoted_body


def test_attachment_payload_is_not_in_body(parser: SafeEmailParser) -> None:
    message = EmailMessage()
    message["From"] = "sender@example.test"
    message["To"] = "qa@example.test"
    message["Subject"] = "附件安全测试"
    message.set_content("只处理这一段正文")
    message.add_attachment(
        b"SECRET_ATTACHMENT_BODY",
        maintype="application",
        subtype="octet-stream",
        filename="payload.bin",
    )

    parsed = parser.parse(message.as_bytes())

    assert "只处理这一段正文" in parsed.current_body
    assert "SECRET_ATTACHMENT_BODY" not in parsed.current_body
    assert parsed.attachments[0].filename == "payload.bin"
    assert ParseWarningCode.ATTACHMENTS_IGNORED in parsed.warnings


def test_missing_body_is_rejected(parser: SafeEmailParser) -> None:
    raw = b"From: sender@example.test\r\nTo: qa@example.test\r\nSubject: no body\r\n\r\n"
    with pytest.raises(EmailParseError) as captured:
        parser.parse(raw)
    assert captured.value.code == "body_required"


@pytest.mark.parametrize(
    "raw",
    [
        b"arbitrary bytes are not an email",
        b"\r\n\r\nbody without headers",
        b"From: sender@example.test\r\n\r\nbody\x00suffix",
    ],
)
def test_invalid_message_structure_is_rejected(parser: SafeEmailParser, raw: bytes) -> None:
    with pytest.raises(EmailParseError) as captured:
        parser.parse(raw)
    assert captured.value.code == "invalid_message_structure"


def test_body_character_limit_is_enforced() -> None:
    parser = SafeEmailParser(
        max_body_chars=10,
        max_header_count=20,
        max_header_value_chars=1_000,
        max_mime_depth=3,
        max_mime_parts=10,
    )
    raw = b"From: a@example.test\r\nContent-Type: text/plain\r\n\r\n12345678901"
    with pytest.raises(EmailParseError) as captured:
        parser.parse(raw)
    assert captured.value.code == "clean_body_too_large"


def test_header_count_limit_is_enforced() -> None:
    parser = SafeEmailParser(
        max_body_chars=1_000,
        max_header_count=2,
        max_header_value_chars=1_000,
        max_mime_depth=3,
        max_mime_parts=10,
    )
    raw = b"From: a@example.test\r\nTo: b@example.test\r\nX-Extra: value\r\n\r\nbody"
    with pytest.raises(EmailParseError, match="邮件头数量") as captured:
        parser.parse(raw)
    assert captured.value.code == "too_many_headers"


def test_header_value_limit_is_enforced() -> None:
    parser = SafeEmailParser(
        max_body_chars=1_000,
        max_header_count=20,
        max_header_value_chars=5,
        max_mime_depth=3,
        max_mime_parts=10,
    )
    raw = b"Subject: 123456\r\n\r\nbody"
    with pytest.raises(EmailParseError) as captured:
        parser.parse(raw)
    assert captured.value.code == "header_too_large"


def test_mime_part_limit_is_enforced() -> None:
    message = EmailMessage()
    message.make_mixed()
    for value in ("one", "two", "three"):
        part = EmailMessage()
        part.set_content(value)
        message.attach(part)

    parser = SafeEmailParser(
        max_body_chars=1_000,
        max_header_count=20,
        max_header_value_chars=1_000,
        max_mime_depth=3,
        max_mime_parts=3,
    )
    with pytest.raises(EmailParseError) as captured:
        parser.parse(message.as_bytes())
    assert captured.value.code == "too_many_mime_parts"


def test_mime_depth_limit_is_enforced() -> None:
    root = EmailMessage()
    root.make_mixed()
    nested = EmailMessage()
    nested.make_mixed()
    body = EmailMessage()
    body.set_content("body")
    nested.attach(body)
    root.attach(nested)

    parser = SafeEmailParser(
        max_body_chars=1_000,
        max_header_count=20,
        max_header_value_chars=1_000,
        max_mime_depth=1,
        max_mime_parts=10,
    )
    with pytest.raises(EmailParseError) as captured:
        parser.parse(root.as_bytes())
    assert captured.value.code == "mime_too_deep"

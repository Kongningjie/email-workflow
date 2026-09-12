from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from email import policy
from email.headerregistry import BaseHeader
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from typing import ClassVar, cast

import nh3

from email_workflow.domain.email import AttachmentMetadata, ParsedEmail, ParseWarningCode


class EmailParseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _PlainTextExtractor(HTMLParser):
    _BLOCK_TAGS: ClassVar[set[str]] = {
        "address",
        "article",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "p",
        "section",
        "table",
        "tr",
    }
    _CELL_TAGS: ClassVar[set[str]] = {"td", "th"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in self._CELL_TAGS:
            self.parts.append("\t")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


class SafeEmailParser:
    _ALLOWED_HTML_TAGS: ClassVar[set[str]] = {
        "address",
        "article",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "section",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
    _QUOTE_PATTERNS = (
        re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE),
        re.compile(r"^\s*-{2,}\s*Forwarded message\s*-{2,}\s*$", re.IGNORECASE),
        re.compile(r"^\s*On .+ wrote:\s*$", re.IGNORECASE),
        re.compile(r"^\s*在.+写道[：:]\s*$"),  # noqa: RUF001
    )
    _SIGNATURE_PATTERNS = (
        re.compile(r"^--\s*$"),
        re.compile(r"^Sent from my .+$", re.IGNORECASE),
        re.compile(r"^从我的.+发送$"),
    )
    _LEGAL_PATTERNS = (
        re.compile(r"^confidentiality notice\b", re.IGNORECASE),
        re.compile(r"^本邮件及其附件可能包含保密信息"),
    )
    _ACTIVE_HTML = re.compile(r"<(script|iframe|object|embed|form)\b|\son[a-z]+\s*=", re.IGNORECASE)
    _REMOTE_HTML = re.compile(r"\s(?:src|href)\s*=\s*['\"]?\s*(?:https?:|//|data:)", re.IGNORECASE)

    def __init__(
        self,
        *,
        max_body_chars: int,
        max_header_count: int,
        max_header_value_chars: int,
        max_mime_depth: int,
        max_mime_parts: int,
    ) -> None:
        self.max_body_chars = max_body_chars
        self.max_header_count = max_header_count
        self.max_header_value_chars = max_header_value_chars
        self.max_mime_depth = max_mime_depth
        self.max_mime_parts = max_mime_parts

    def parse(self, raw: bytes) -> ParsedEmail:
        self._validate_raw_structure(raw)
        try:
            message = BytesParser(policy=policy.default).parsebytes(raw)
        except Exception as exc:
            raise EmailParseError("invalid_message_structure", "邮件结构无法解析") from exc
        if not isinstance(message, EmailMessage):
            raise EmailParseError("invalid_message_structure", "邮件结构无法解析")

        self._validate_headers(message)
        warnings: set[ParseWarningCode] = set()
        body_parts, attachments = self._collect_parts(message, warnings)
        plain_parts = [text for content_type, text in body_parts if content_type == "text/plain"]
        html_parts = [text for content_type, text in body_parts if content_type == "text/html"]
        if plain_parts:
            body = "\n\n".join(plain_parts)
        elif html_parts:
            body = "\n\n".join(self._html_to_text(value, warnings) for value in html_parts)
        else:
            raise EmailParseError("body_required", "邮件必须包含非空文本或 HTML 正文")

        normalized = self._normalize_text(body)
        current_body, quoted_body, uncertain = self._partition_quotes(normalized)
        current_body = self._remove_noise(current_body)
        quoted_body = self._remove_noise(quoted_body)
        if uncertain:
            warnings.add(ParseWarningCode.QUOTE_BOUNDARY_UNCERTAIN)
        if not current_body and not quoted_body:
            raise EmailParseError("body_required", "邮件清洗后没有有效正文")
        if len(current_body) + len(quoted_body) > self.max_body_chars:
            raise EmailParseError("clean_body_too_large", "邮件清洗后正文超过字符限制")

        subject = self._optional_header(message["Subject"])
        sender = self._optional_header(message["From"])
        recipients = self._recipients(message)
        sent_at = self._sent_at(message)
        return ParsedEmail(
            subject=subject,
            sender=sender,
            recipients=recipients,
            sent_at=sent_at,
            current_body=current_body,
            quoted_body=quoted_body,
            attachments=tuple(attachments),
            warnings=tuple(sorted(warnings, key=str)),
        )

    @staticmethod
    def _validate_raw_structure(raw: bytes) -> None:
        if b"\x00" in raw:
            raise EmailParseError("invalid_message_structure", "邮件结构无法解析")
        separator = re.search(rb"\r\n\r\n|\n\n|\r\r", raw)
        if separator is None:
            raise EmailParseError("invalid_message_structure", "邮件结构无法解析")
        header_block = raw[: separator.start()]
        header_pattern = re.compile(rb"^[!-9;-~]+:[^\r\n]*$", re.MULTILINE)
        if not header_pattern.search(header_block):
            raise EmailParseError("invalid_message_structure", "邮件结构无法解析")

    def _validate_headers(self, message: EmailMessage) -> None:
        total_headers = 0
        stack = [message]
        while stack:
            part = stack.pop()
            items = list(part.raw_items())
            total_headers += len(items)
            if total_headers > self.max_header_count:
                raise EmailParseError("too_many_headers", "邮件头数量超过限制")
            for _, value in items:
                if len(value) > self.max_header_value_chars:
                    raise EmailParseError("header_too_large", "邮件头字段超过长度限制")
            if part.is_multipart() and part.get_content_disposition() != "attachment":
                stack.extend(
                    cast(EmailMessage, child) for child in reversed(list(part.iter_parts()))
                )

    def _collect_parts(
        self,
        message: EmailMessage,
        warnings: set[ParseWarningCode],
    ) -> tuple[list[tuple[str, str]], list[AttachmentMetadata]]:
        part_count = 0

        def visit(
            part: EmailMessage, depth: int
        ) -> tuple[list[tuple[str, str]], list[AttachmentMetadata]]:
            nonlocal part_count
            part_count += 1
            if part_count > self.max_mime_parts:
                raise EmailParseError("too_many_mime_parts", "MIME 部件数量超过限制")
            if depth > self.max_mime_depth:
                raise EmailParseError("mime_too_deep", "MIME 嵌套深度超过限制")
            if part.get_content_disposition() == "attachment" or part.get_filename():
                warnings.add(ParseWarningCode.ATTACHMENTS_IGNORED)
                return [], [self._attachment_metadata(part)]
            if part.is_multipart():
                child_results = [
                    visit(cast(EmailMessage, child), depth + 1) for child in part.iter_parts()
                ]
                attachments = [item for _, values in child_results for item in values]
                if part.get_content_subtype() == "alternative":
                    bodies = self._preferred_alternative(child_results)
                else:
                    bodies = [item for values, _ in child_results for item in values]
                return bodies, attachments
            content_type = part.get_content_type().lower()
            if content_type not in {"text/plain", "text/html"}:
                return [], []
            text = self._decode_text_part(part, warnings)
            return ([(content_type, text)] if text.strip() else []), []

        return visit(message, 0)

    @staticmethod
    def _preferred_alternative(
        results: Iterable[tuple[list[tuple[str, str]], list[AttachmentMetadata]]],
    ) -> list[tuple[str, str]]:
        flattened = [item for bodies, _ in results for item in bodies]
        plain = [item for item in flattened if item[0] == "text/plain"]
        if plain:
            return plain[:1]
        html = [item for item in flattened if item[0] == "text/html"]
        return html[:1]

    @staticmethod
    def _decode_text_part(part: EmailMessage, warnings: set[ParseWarningCode]) -> str:
        payload = part.get_payload(decode=True)
        if payload is None:
            undecoded = part.get_payload(decode=False)
            return undecoded if isinstance(undecoded, str) else ""
        if not isinstance(payload, bytes):
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if "\ufffd" in text:
            warnings.add(ParseWarningCode.CHARACTER_REPLACED)
        return text

    @staticmethod
    def _attachment_metadata(part: EmailMessage) -> AttachmentMetadata:
        filename = SafeEmailParser._clean_metadata(part.get_filename() or "unnamed")
        payload = part.get_payload(decode=False)
        if isinstance(payload, str):
            encoded_size = len(payload.encode("utf-8", errors="replace"))
        elif isinstance(payload, bytes):
            encoded_size = len(payload)
        else:
            encoded_size = 0
        return AttachmentMetadata(
            filename=filename,
            content_type=SafeEmailParser._clean_metadata(part.get_content_type()),
            encoded_size_bytes=encoded_size,
        )

    @staticmethod
    def _clean_metadata(value: str) -> str:
        return "".join(character for character in value if character.isprintable())[:255]

    def _html_to_text(self, html: str, warnings: set[ParseWarningCode]) -> str:
        if self._ACTIVE_HTML.search(html):
            warnings.add(ParseWarningCode.ACTIVE_CONTENT_REMOVED)
        if self._REMOTE_HTML.search(html):
            warnings.add(ParseWarningCode.REMOTE_RESOURCE_REMOVED)
        clean_html = nh3.clean(
            html,
            tags=self._ALLOWED_HTML_TAGS,
            attributes={},
            url_schemes=set(),
            strip_comments=True,
        )
        extractor = _PlainTextExtractor()
        extractor.feed(clean_html)
        extractor.close()
        return extractor.text()

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = unicodedata.normalize("NFKC", value.replace("\r\n", "\n").replace("\r", "\n"))
        lines = [re.sub(r"[ \t]+$", "", line) for line in value.split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    def _partition_quotes(self, value: str) -> tuple[str, str, bool]:
        lines = value.split("\n")
        for index, line in enumerate(lines):
            if any(pattern.match(line) for pattern in self._QUOTE_PATTERNS):
                return "\n".join(lines[:index]).strip(), "\n".join(lines[index:]).strip(), False
        quoted_lines = sum(1 for line in lines if line.lstrip().startswith(">"))
        uncertain = quoted_lines >= 3
        return value, "", uncertain

    def _remove_noise(self, value: str) -> str:
        if not value:
            return ""
        lines = value.split("\n")
        for index, line in enumerate(lines):
            if any(pattern.match(line) for pattern in self._SIGNATURE_PATTERNS):
                lines = lines[:index]
                break
            if any(pattern.match(line) for pattern in self._LEGAL_PATTERNS):
                lines = lines[:index]
                break
        return self._normalize_text("\n".join(lines))

    @staticmethod
    def _optional_header(header: BaseHeader | str | None) -> str | None:
        if header is None:
            return None
        value = SafeEmailParser._clean_metadata(str(header)).strip()
        return value or None

    @staticmethod
    def _recipients(message: EmailMessage) -> tuple[str, ...]:
        values = [str(value) for name in ("To", "Cc", "Bcc") for value in message.get_all(name, [])]
        addresses = [address for _, address in getaddresses(values) if address]
        return tuple(dict.fromkeys(addresses))

    @staticmethod
    def _sent_at(message: EmailMessage) -> datetime | None:
        value = message.get("Date")
        if value is None:
            return None
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SectionType(StrEnum):
    SUBJECT = "subject"
    SENDER = "sender"
    RECIPIENTS = "recipients"
    SENT_AT = "sent_at"
    CURRENT_BODY = "current_body"
    QUOTED_BODY = "quoted_body"


class ParseWarningCode(StrEnum):
    ACTIVE_CONTENT_REMOVED = "active_content_removed"
    REMOTE_RESOURCE_REMOVED = "remote_resource_removed"
    ATTACHMENTS_IGNORED = "attachments_ignored"
    QUOTE_BOUNDARY_UNCERTAIN = "quote_boundary_uncertain"
    CHARACTER_REPLACED = "character_replaced"


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    filename: str
    content_type: str
    encoded_size_bytes: int


@dataclass(frozen=True, slots=True)
class ParsedEmail:
    subject: str | None
    sender: str | None
    recipients: tuple[str, ...]
    sent_at: datetime | None
    current_body: str
    quoted_body: str
    attachments: tuple[AttachmentMetadata, ...] = ()
    warnings: tuple[ParseWarningCode, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceDraft:
    section_type: SectionType
    segment_index: int
    start_offset: int
    end_offset: int
    text: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class CleanupReport:
    dry_run: bool
    raw_import_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_segment_ids: tuple[str, ...] = field(default_factory=tuple)

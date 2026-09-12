from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_workflow.application.evidence import EvidenceSegmenter
from email_workflow.domain.email import CleanupReport, ParseWarningCode
from email_workflow.infrastructure.email_parser import EmailParseError, SafeEmailParser
from email_workflow.infrastructure.import_repository import ImportRepository
from email_workflow.infrastructure.models import EvidenceSegment, ImportedEmail
from email_workflow.infrastructure.storage import ImportStorage


class Clock(Protocol):
    def now(self) -> datetime: ...


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported_email: ImportedEmail
    deduplicated: bool
    warnings: tuple[ParseWarningCode, ...] = ()


class EmailImportService:
    _ALLOWED_CONTENT_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"message/rfc822", "application/octet-stream"}
    )

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        parser: SafeEmailParser,
        segmenter: EvidenceSegmenter,
        storage: ImportStorage,
        max_upload_bytes: int,
        raw_retention_hours: int,
        evidence_retention_days: int,
        clock: Clock | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.parser = parser
        self.segmenter = segmenter
        self.storage = storage
        self.max_upload_bytes = max_upload_bytes
        self.raw_retention_hours = raw_retention_hours
        self.evidence_retention_days = evidence_retention_days
        self.clock = clock or UtcClock()

    async def import_email(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        raw: bytes,
        external_processing_confirmed: bool,
    ) -> ImportResult:
        safe_filename = self._validate_upload(
            filename=filename,
            content_type=content_type,
            raw=raw,
            external_processing_confirmed=external_processing_confirmed,
        )
        content_sha256 = hashlib.sha256(raw).hexdigest()
        async with self.session_factory() as session:
            repository = ImportRepository(session)
            existing = await repository.find_by_hash(content_sha256)
            if existing is not None:
                return ImportResult(imported_email=existing, deduplicated=True)

            now = self.clock.now()
            imported = ImportedEmail(
                original_filename=safe_filename,
                subject=None,
                sender=None,
                recipients=[],
                sent_at=None,
                content_sha256=content_sha256,
                parse_status="parsing",
                extraction_status="not_started",
                safe_error_summary=None,
                raw_expires_at=now + timedelta(hours=self.raw_retention_hours),
                purged_at=None,
            )
            repository.add_import(imported)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                concurrent = await repository.find_by_hash(content_sha256)
                if concurrent is None:
                    raise
                return ImportResult(imported_email=concurrent, deduplicated=True)

            try:
                self.storage.write_import(imported.id, raw, None)
                parsed = self.parser.parse(raw)
                self.storage.write_import(imported.id, raw, parsed)
                imported.subject = parsed.subject
                imported.sender = parsed.sender
                imported.recipients = list(parsed.recipients)
                imported.sent_at = parsed.sent_at
                imported.parse_status = "parsed"
                expires_at = now + timedelta(days=self.evidence_retention_days)
                evidence = [
                    EvidenceSegment(
                        source_item_id=imported.id,
                        section_type=draft.section_type.value,
                        segment_index=draft.segment_index,
                        start_offset=draft.start_offset,
                        end_offset=draft.end_offset,
                        safe_excerpt=draft.text,
                        content_sha256=draft.content_sha256,
                        expires_at=expires_at,
                        purged_at=None,
                    )
                    for draft in self.segmenter.segment(parsed)
                ]
                repository.add_evidence(evidence)
                await session.commit()
                return ImportResult(
                    imported_email=imported,
                    deduplicated=False,
                    warnings=parsed.warnings,
                )
            except EmailParseError as exc:
                imported.parse_status = "parse_failed"
                imported.safe_error_summary = exc.code
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    self.storage.purge_import_content(imported.id, dry_run=False)
                    raise
                return ImportResult(imported_email=imported, deduplicated=False)
            except Exception:
                await session.rollback()
                self.storage.purge_import_content(imported.id, dry_run=False)
                raise

    async def get_import(self, import_id: uuid.UUID) -> ImportedEmail | None:
        async with self.session_factory() as session:
            return await ImportRepository(session).get(import_id)

    async def get_evidence(self, segment_id: uuid.UUID) -> EvidenceSegment | None:
        async with self.session_factory() as session:
            return await ImportRepository(session).get_evidence(segment_id)

    def _validate_upload(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        raw: bytes,
        external_processing_confirmed: bool,
    ) -> str:
        if not external_processing_confirmed:
            raise EmailParseError("external_processing_not_confirmed", "必须确认邮件外发处理声明")
        if not filename or not filename.lower().endswith(".eml"):
            raise EmailParseError("invalid_file_extension", "仅支持 .eml 文件")
        safe_filename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        safe_filename = "".join(character for character in safe_filename if character.isprintable())
        if not safe_filename or len(safe_filename) > 255:
            raise EmailParseError("invalid_filename", "文件名不符合要求")
        normalized_content_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
        if normalized_content_type not in self._ALLOWED_CONTENT_TYPES:
            raise EmailParseError("invalid_content_type", "文件 MIME 类型不符合要求")
        if not raw:
            raise EmailParseError("empty_file", "邮件文件不能为空")
        if len(raw) > self.max_upload_bytes:
            raise EmailParseError("file_too_large", "邮件文件超过 5 MiB 限制")
        return safe_filename


class RetentionCleanupService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ImportStorage,
        clock: Clock | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.clock = clock or UtcClock()

    async def cleanup(self, *, dry_run: bool) -> CleanupReport:
        now = self.clock.now()
        async with self.session_factory() as session:
            repository = ImportRepository(session)
            imports = await repository.expired_imports(now)
            evidence = await repository.expired_evidence(now)
            import_ids = tuple(str(item.id) for item in imports)
            evidence_ids = tuple(str(item.id) for item in evidence)
            if dry_run:
                return CleanupReport(
                    dry_run=True,
                    raw_import_ids=import_ids,
                    evidence_segment_ids=evidence_ids,
                )
            for imported in imports:
                self.storage.purge_import_content(imported.id, dry_run=False)
                imported.purged_at = now
            for segment in evidence:
                segment.safe_excerpt = None
                segment.purged_at = now
            await session.commit()
            return CleanupReport(
                dry_run=False,
                raw_import_ids=import_ids,
                evidence_segment_ids=evidence_ids,
            )

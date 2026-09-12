from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from email_workflow.infrastructure.models import EvidenceSegment, ImportedEmail


class ImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_hash(self, content_sha256: str) -> ImportedEmail | None:
        statement = select(ImportedEmail).where(ImportedEmail.content_sha256 == content_sha256)
        return cast(ImportedEmail | None, await self.session.scalar(statement))

    async def get(self, import_id: uuid.UUID) -> ImportedEmail | None:
        return await self.session.get(ImportedEmail, import_id)

    def add_import(self, imported_email: ImportedEmail) -> None:
        self.session.add(imported_email)

    def add_evidence(self, evidence: list[EvidenceSegment]) -> None:
        self.session.add_all(evidence)

    async def expired_imports(self, now: datetime) -> list[ImportedEmail]:
        statement = (
            select(ImportedEmail)
            .where(ImportedEmail.raw_expires_at <= now, ImportedEmail.purged_at.is_(None))
            .order_by(ImportedEmail.created_at, ImportedEmail.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def expired_evidence(self, now: datetime) -> list[EvidenceSegment]:
        statement = (
            select(EvidenceSegment)
            .where(EvidenceSegment.expires_at <= now, EvidenceSegment.purged_at.is_(None))
            .order_by(EvidenceSegment.created_at, EvidenceSegment.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def evidence_for_import(self, import_id: uuid.UUID) -> list[EvidenceSegment]:
        statement = (
            select(EvidenceSegment)
            .where(EvidenceSegment.source_item_id == import_id)
            .order_by(EvidenceSegment.segment_index)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_evidence(self, segment_id: uuid.UUID) -> EvidenceSegment | None:
        return await self.session.get(EvidenceSegment, segment_id)


def imported_email_snapshot(imported: ImportedEmail) -> dict[str, Any]:
    return {
        "id": imported.id,
        "original_filename": imported.original_filename,
        "subject": imported.subject,
        "sender": imported.sender,
        "recipients": imported.recipients,
        "sent_at": imported.sent_at,
        "content_sha256": imported.content_sha256,
        "parse_status": imported.parse_status,
        "extraction_status": imported.extraction_status,
        "safe_error_summary": imported.safe_error_summary,
        "created_at": imported.created_at,
        "raw_expires_at": imported.raw_expires_at,
        "purged_at": imported.purged_at,
    }

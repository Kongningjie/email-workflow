from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from email_workflow.application.evidence import EvidenceSegmenter
from email_workflow.application.imports import (
    EmailImportService,
    RetentionCleanupService,
)
from email_workflow.infrastructure.database import create_engine, create_session_factory
from email_workflow.infrastructure.email_parser import EmailParseError, SafeEmailParser
from email_workflow.infrastructure.import_repository import ImportRepository
from email_workflow.infrastructure.models import Base, ImportedEmail
from email_workflow.infrastructure.storage import ImportStorage

pytestmark = pytest.mark.postgres


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


@pytest_asyncio.fixture
async def postgres_session_factory() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("未配置独立 PostgreSQL 测试库")
    if not database_url.rstrip("/").endswith("email_workflow_test"):
        pytest.fail("TEST_DATABASE_URL 必须指向 email_workflow_test")
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine, create_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


def build_service(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: ImportStorage,
    clock: FixedClock,
) -> EmailImportService:
    parser = SafeEmailParser(
        max_body_chars=200_000,
        max_header_count=200,
        max_header_value_chars=16_384,
        max_mime_depth=10,
        max_mime_parts=100,
    )
    return EmailImportService(
        session_factory=session_factory,
        parser=parser,
        segmenter=EvidenceSegmenter(segment_chars=1_000, overlap_chars=100),
        storage=storage,
        max_upload_bytes=5 * 1024 * 1024,
        raw_retention_hours=24,
        evidence_retention_days=90,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_import_deduplication_evidence_and_retention(
    postgres_session_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, session_factory = postgres_session_factory
    imported_at = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)
    storage = ImportStorage(tmp_path)
    service = build_service(
        session_factory=session_factory,
        storage=storage,
        clock=FixedClock(imported_at),
    )
    raw = Path("tests/fixtures/eml/02-html-multi-domain-table.eml").read_bytes()

    first = await service.import_email(
        filename="fixture.eml",
        content_type="message/rfc822",
        raw=raw,
        external_processing_confirmed=True,
    )
    duplicate = await service.import_email(
        filename="duplicate.eml",
        content_type="application/octet-stream",
        raw=raw,
        external_processing_confirmed=True,
    )

    assert first.deduplicated is False
    assert first.imported_email.parse_status == "parsed"
    assert duplicate.deduplicated is True
    assert duplicate.imported_email.id == first.imported_email.id
    async with session_factory() as session:
        evidence = await ImportRepository(session).evidence_for_import(first.imported_email.id)
    assert evidence
    assert all(len(segment.content_sha256) == 64 for segment in evidence)
    assert (tmp_path / "imports" / str(first.imported_email.id) / "original.eml").is_file()

    cleanup = RetentionCleanupService(
        session_factory=session_factory,
        storage=storage,
        clock=FixedClock(imported_at + timedelta(days=91)),
    )
    preview = await cleanup.cleanup(dry_run=True)
    assert str(first.imported_email.id) in preview.raw_import_ids
    assert evidence[0].safe_excerpt is not None

    await cleanup.cleanup(dry_run=False)
    async with session_factory() as session:
        refreshed = await ImportRepository(session).get(first.imported_email.id)
        refreshed_evidence = await ImportRepository(session).evidence_for_import(
            first.imported_email.id
        )
    assert refreshed is not None and refreshed.purged_at is not None
    assert all(segment.safe_excerpt is None for segment in refreshed_evidence)
    assert not (tmp_path / "imports" / str(first.imported_email.id) / "original.eml").exists()


@pytest.mark.asyncio
async def test_parse_failure_is_recorded_and_raw_is_retained(
    postgres_session_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, session_factory = postgres_session_factory
    service = build_service(
        session_factory=session_factory,
        storage=ImportStorage(tmp_path),
        clock=FixedClock(datetime(2026, 9, 12, 8, 0, tzinfo=UTC)),
    )
    raw = b"From: sender@example.test\r\nSubject: missing body\r\n\r\n"

    result = await service.import_email(
        filename="invalid.eml",
        content_type="message/rfc822",
        raw=raw,
        external_processing_confirmed=True,
    )

    assert result.imported_email.parse_status == "parse_failed"
    assert result.imported_email.safe_error_summary == "body_required"
    raw_path = tmp_path / "imports" / str(result.imported_email.id) / "original.eml"
    assert raw_path.read_bytes() == raw


@pytest.mark.asyncio
async def test_concurrent_duplicate_import_creates_one_record(
    postgres_session_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, session_factory = postgres_session_factory
    service = build_service(
        session_factory=session_factory,
        storage=ImportStorage(tmp_path),
        clock=FixedClock(datetime(2026, 9, 12, 8, 0, tzinfo=UTC)),
    )
    raw = Path("tests/fixtures/eml/01-plain-single-domain.eml").read_bytes()

    first, second = await asyncio.gather(
        service.import_email(
            filename="../../first.eml",
            content_type="message/rfc822",
            raw=raw,
            external_processing_confirmed=True,
        ),
        service.import_email(
            filename="second.eml",
            content_type="message/rfc822",
            raw=raw,
            external_processing_confirmed=True,
        ),
    )

    assert first.imported_email.id == second.imported_email.id
    assert sorted((first.deduplicated, second.deduplicated)) == [False, True]
    assert first.imported_email.original_filename == "first.eml"
    async with session_factory() as session:
        record_count = await session.scalar(select(func.count()).select_from(ImportedEmail))
    assert record_count == 1


@pytest.mark.asyncio
async def test_hard_upload_rejections_leave_no_record_or_file(
    postgres_session_factory: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path: Path,
) -> None:
    _, session_factory = postgres_session_factory
    storage = ImportStorage(tmp_path)
    service = build_service(
        session_factory=session_factory,
        storage=storage,
        clock=FixedClock(datetime(2026, 9, 12, 8, 0, tzinfo=UTC)),
    )
    valid_raw = b"From: sender@example.test\r\n\r\nbody"
    rejected_uploads = (
        ("mail.txt", "message/rfc822", valid_raw, True, "invalid_file_extension"),
        ("mail.eml", "message/rfc822", b"", True, "empty_file"),
        ("mail.eml", "message/rfc822", b"x" * (5 * 1024 * 1024 + 1), True, "file_too_large"),
        (
            "mail.eml",
            "message/rfc822",
            valid_raw,
            False,
            "external_processing_not_confirmed",
        ),
    )

    for filename, content_type, raw, confirmed, expected_code in rejected_uploads:
        with pytest.raises(EmailParseError) as captured:
            await service.import_email(
                filename=filename,
                content_type=content_type,
                raw=raw,
                external_processing_confirmed=confirmed,
            )
        assert captured.value.code == expected_code

    async with session_factory() as session:
        record_count = await session.scalar(select(func.count()).select_from(ImportedEmail))
    assert record_count == 0
    assert not (tmp_path / "imports").exists()

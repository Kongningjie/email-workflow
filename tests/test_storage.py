import json
import uuid
from pathlib import Path

import pytest

from email_workflow.domain.email import (
    AttachmentMetadata,
    ParsedEmail,
    ParseWarningCode,
    SectionType,
)
from email_workflow.infrastructure.storage import ImportStorage


def test_storage_writes_manifest_and_purges_only_known_files(tmp_path: Path) -> None:
    storage = ImportStorage(tmp_path)
    import_id = uuid.uuid4()
    parsed = ParsedEmail(
        subject="主题",
        sender="sender@example.test",
        recipients=("qa@example.test",),
        sent_at=None,
        current_body="当前正文",
        quoted_body="引用正文",
        attachments=(AttachmentMetadata("fixture.bin", "application/octet-stream", 12),),
        warnings=(ParseWarningCode.ATTACHMENTS_IGNORED,),
    )

    storage.write_import(import_id, b"raw email", parsed)

    directory = tmp_path / "imports" / str(import_id)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert storage.read_section(import_id, SectionType.CURRENT_BODY) == "当前正文"
    assert manifest["attachments"][0]["filename"] == "fixture.bin"
    assert "SECRET_ATTACHMENT_BODY" not in json.dumps(manifest)
    assert storage.purge_import_content(import_id, dry_run=True) is True
    assert (directory / "original.eml").exists()

    assert storage.purge_import_content(import_id, dry_run=False) is True
    assert not (directory / "original.eml").exists()
    assert list(directory.iterdir()) == []


def test_storage_rejects_non_body_section(tmp_path: Path) -> None:
    storage = ImportStorage(tmp_path)
    with pytest.raises(ValueError, match="仅正文证据"):
        storage.read_section(uuid.uuid4(), SectionType.SUBJECT)

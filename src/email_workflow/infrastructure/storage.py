from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from email_workflow.domain.email import ParsedEmail, SectionType


class ImportStorage:
    _PURGE_FILES = ("original.eml", "current_body.txt", "quoted_body.txt", "manifest.json")

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write_import(self, import_id: uuid.UUID, raw: bytes, parsed: ParsedEmail | None) -> None:
        directory = self._import_directory(import_id)
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_write(directory / "original.eml", raw)
        if parsed is None:
            return
        self._atomic_write(directory / "current_body.txt", parsed.current_body.encode("utf-8"))
        self._atomic_write(directory / "quoted_body.txt", parsed.quoted_body.encode("utf-8"))
        manifest: dict[str, Any] = {
            "version": "1.0",
            "attachments": [
                {
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "encoded_size_bytes": item.encoded_size_bytes,
                }
                for item in parsed.attachments
            ],
            "warnings": [str(item) for item in parsed.warnings],
        }
        self._atomic_write(
            directory / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def read_section(self, import_id: uuid.UUID, section_type: SectionType) -> str:
        filenames = {
            SectionType.CURRENT_BODY: "current_body.txt",
            SectionType.QUOTED_BODY: "quoted_body.txt",
        }
        try:
            filename = filenames[section_type]
        except KeyError as exc:
            raise ValueError("仅正文证据保存在短期文件中") from exc
        return self._safe_path(self._import_directory(import_id) / filename).read_text(
            encoding="utf-8"
        )

    def purge_import_content(self, import_id: uuid.UUID, *, dry_run: bool) -> bool:
        directory = self._import_directory(import_id)
        existing = [path for name in self._PURGE_FILES if (path := directory / name).is_file()]
        if not existing:
            return False
        if not dry_run:
            for path in existing:
                self._safe_path(path).unlink(missing_ok=True)
        return True

    def _import_directory(self, import_id: uuid.UUID) -> Path:
        return self._safe_path(self.root / "imports" / str(import_id))

    def _safe_path(self, candidate: Path) -> Path:
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise ValueError("文件路径超出受控数据目录")
        return resolved

    def _atomic_write(self, destination: Path, content: bytes) -> None:
        safe_destination = self._safe_path(destination)
        temporary = self._safe_path(
            safe_destination.with_name(f".{safe_destination.name}.{uuid.uuid4().hex}.tmp")
        )
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, safe_destination)
        finally:
            temporary.unlink(missing_ok=True)

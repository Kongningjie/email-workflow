from __future__ import annotations

import argparse
import asyncio
import json

from email_workflow.application.imports import RetentionCleanupService
from email_workflow.core.config import get_settings
from email_workflow.infrastructure.database import create_engine, create_session_factory
from email_workflow.infrastructure.storage import ImportStorage


async def run_cleanup(*, dry_run: bool) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        service = RetentionCleanupService(
            session_factory=create_session_factory(engine),
            storage=ImportStorage(settings.data_dir),
        )
        report = await service.cleanup(dry_run=dry_run)
        print(
            json.dumps(
                {
                    "dry_run": report.dry_run,
                    "raw_import_ids": report.raw_import_ids,
                    "evidence_segment_ids": report.evidence_segment_ids,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="邮件工作流管理命令")
    subparsers = parser.add_subparsers(dest="command", required=True)
    cleanup_parser = subparsers.add_parser("cleanup", help="清理过期短期数据")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="仅列出待清理记录")
    arguments = parser.parse_args()
    if arguments.command == "cleanup":
        return asyncio.run(run_cleanup(dry_run=bool(arguments.dry_run)))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

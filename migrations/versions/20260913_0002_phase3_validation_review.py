"""Align validation issues and review decisions with phase 3 contracts.

Revision ID: 20260913_0002
Revises: 20260911_0001
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260913_0002"
down_revision: str | None = "20260911_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_plan_content_sha256", "test_plan_versions", type_="unique")
    op.drop_constraint("ck_issue_severity", "validation_issues", type_="check")
    op.create_check_constraint(
        "ck_issue_severity",
        "validation_issues",
        "severity IN ('blocking','warning','info')",
    )
    op.add_column("validation_issues", sa.Column("suggestion", sa.String(500)))
    op.create_unique_constraint(
        "uq_review_version_decision", "review_records", ["test_plan_version_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_review_version_decision", "review_records", type_="unique")
    op.drop_column("validation_issues", "suggestion")
    op.drop_constraint("ck_issue_severity", "validation_issues", type_="check")
    op.create_check_constraint(
        "ck_issue_severity",
        "validation_issues",
        "severity IN ('blocking','warning')",
    )
    op.create_unique_constraint(
        "uq_plan_content_sha256", "test_plan_versions", ["test_plan_id", "content_sha256"]
    )

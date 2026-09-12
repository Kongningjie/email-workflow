from email_workflow.infrastructure.models import Base


def test_initial_metadata_contains_full_core_schema() -> None:
    expected = {
        "imported_emails",
        "evidence_segments",
        "test_plans",
        "test_plan_versions",
        "validation_runs",
        "validation_issues",
        "review_records",
        "payload_previews",
        "submissions",
        "submission_attempts",
        "audit_events",
    }
    assert set(Base.metadata.tables) == expected

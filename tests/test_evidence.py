from datetime import UTC, datetime

from email_workflow.application.evidence import EvidenceSegmenter, rebuild_evidence_text
from email_workflow.domain.email import ParsedEmail, SectionType


def test_segments_overlap_and_rebuild_from_normalized_source() -> None:
    body = "A" * 2_500
    parsed = ParsedEmail(
        subject="主题",
        sender="sender@example.test",
        recipients=("qa@example.test",),
        sent_at=datetime(2026, 9, 12, tzinfo=UTC),
        current_body=body,
        quoted_body="",
    )
    segmenter = EvidenceSegmenter(segment_chars=1_000, overlap_chars=100)

    segments = segmenter.segment(parsed)
    body_segments = [item for item in segments if item.section_type is SectionType.CURRENT_BODY]

    assert [(item.start_offset, item.end_offset) for item in body_segments] == [
        (0, 1_000),
        (900, 1_900),
        (1_800, 2_500),
    ]
    assert all(rebuild_evidence_text(body, item) for item in body_segments)
    assert [item.segment_index for item in segments] == list(range(len(segments)))


def test_tampered_evidence_does_not_rebuild() -> None:
    parsed = ParsedEmail(
        subject=None,
        sender=None,
        recipients=(),
        sent_at=None,
        current_body="可信正文",
        quoted_body="",
    )
    draft = EvidenceSegmenter(segment_chars=100, overlap_chars=10).segment(parsed)[0]
    assert rebuild_evidence_text("被修改的正文", draft) is False

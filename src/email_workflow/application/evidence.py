from __future__ import annotations

import hashlib
from collections.abc import Iterator

from email_workflow.domain.email import EvidenceDraft, ParsedEmail, SectionType


class EvidenceSegmenter:
    def __init__(self, *, segment_chars: int = 1_000, overlap_chars: int = 100) -> None:
        if segment_chars <= 0:
            raise ValueError("证据切片长度必须大于零")
        if overlap_chars < 0 or overlap_chars >= segment_chars:
            raise ValueError("证据重叠长度必须小于切片长度且不得为负数")
        self.segment_chars = segment_chars
        self.overlap_chars = overlap_chars

    def segment(self, parsed: ParsedEmail) -> list[EvidenceDraft]:
        sections = (
            (SectionType.SUBJECT, parsed.subject or ""),
            (SectionType.SENDER, parsed.sender or ""),
            (SectionType.RECIPIENTS, "\n".join(parsed.recipients)),
            (SectionType.SENT_AT, parsed.sent_at.isoformat() if parsed.sent_at else ""),
            (SectionType.CURRENT_BODY, parsed.current_body),
            (SectionType.QUOTED_BODY, parsed.quoted_body),
        )
        drafts: list[EvidenceDraft] = []
        index = 0
        for section_type, text in sections:
            for start, end, segment_text in self._slices(text):
                drafts.append(
                    EvidenceDraft(
                        section_type=section_type,
                        segment_index=index,
                        start_offset=start,
                        end_offset=end,
                        text=segment_text,
                        content_sha256=hashlib.sha256(segment_text.encode("utf-8")).hexdigest(),
                    )
                )
                index += 1
        return drafts

    def _slices(self, text: str) -> Iterator[tuple[int, int, str]]:
        if not text:
            return
        start = 0
        while start < len(text):
            proposed_end = min(start + self.segment_chars, len(text))
            end = self._natural_boundary(text, start, proposed_end)
            if end <= start:
                end = proposed_end
            yield start, end, text[start:end]
            if end == len(text):
                break
            start = max(start + 1, end - self.overlap_chars)

    @staticmethod
    def _natural_boundary(text: str, start: int, proposed_end: int) -> int:
        if proposed_end == len(text):
            return proposed_end
        minimum = start + ((proposed_end - start) * 3 // 4)
        candidates = [text.rfind(marker, minimum, proposed_end) for marker in ("\n", "。", ". ")]
        boundary = max(candidates)
        return boundary + 1 if boundary >= minimum else proposed_end


def rebuild_evidence_text(source_text: str, draft: EvidenceDraft) -> bool:
    if draft.start_offset < 0 or draft.end_offset > len(source_text):
        return False
    rebuilt = source_text[draft.start_offset : draft.end_offset]
    digest = hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
    return rebuilt == draft.text and digest == draft.content_sha256

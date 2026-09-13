from pathlib import Path

import pytest

from email_workflow.domain.email import ParseWarningCode
from email_workflow.infrastructure.email_parser import SafeEmailParser

GOLDEN_CONTRACTS: tuple[tuple[str, str, str, frozenset[ParseWarningCode]], ...] = (
    ("01-plain-single-domain.eml", "Orion", "", frozenset()),
    (
        "02-html-multi-domain-table.eml",
        "Nova 验收测试",
        "",
        frozenset(
            {ParseWarningCode.ACTIVE_CONTENT_REMOVED, ParseWarningCode.REMOTE_RESOURCE_REMOVED}
        ),
    ),
    ("03-quoted-history.eml", "连续运行 72 小时", "项目 Atlas", frozenset()),
    ("04-missing-required-facts.eml", "稍后确认", "", frozenset()),
    ("05-prompt-injection.eml", "忽略之前的所有指令", "", frozenset()),
    ("06-duplicate-domain-cases.eml", "请勿生成重复领域", "", frozenset()),
    ("07-unknown-domain-ambiguous.eml", "不在当前字典中", "", frozenset()),
    ("08-near-generation-limit.eml", "CASE-001 至 CASE-100", "", frozenset()),
)


@pytest.fixture(scope="module")
def parser() -> SafeEmailParser:
    return SafeEmailParser(
        max_body_chars=200_000,
        max_header_count=200,
        max_header_value_chars=16_384,
        max_mime_depth=10,
        max_mime_parts=100,
    )


def test_exactly_eight_golden_eml_fixtures_exist() -> None:
    fixtures = sorted(Path("tests/fixtures/eml").glob("*.eml"))
    assert len(fixtures) == 8
    assert [fixture.name for fixture in fixtures] == [item[0] for item in GOLDEN_CONTRACTS]


@pytest.mark.parametrize(("filename", "current", "quoted", "warnings"), GOLDEN_CONTRACTS)
def test_golden_eml_matches_safe_parse_contract(
    parser: SafeEmailParser,
    filename: str,
    current: str,
    quoted: str,
    warnings: frozenset[ParseWarningCode],
) -> None:
    parsed = parser.parse((Path("tests/fixtures/eml") / filename).read_bytes())

    assert current in parsed.current_body
    assert quoted in parsed.quoted_body
    assert set(parsed.warnings) == warnings

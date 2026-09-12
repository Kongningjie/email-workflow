from email import policy
from email.parser import BytesParser
from pathlib import Path


def test_eight_golden_eml_fixtures_are_parseable() -> None:
    fixtures = sorted(Path("tests/fixtures/eml").glob("*.eml"))
    assert len(fixtures) == 8
    for fixture in fixtures:
        message = BytesParser(policy=policy.default).parsebytes(fixture.read_bytes())
        assert message["From"]
        assert message["To"]
        assert message["Subject"]
        assert message.get_content_type() in {"text/plain", "text/html"}

from pathlib import Path

import pytest

from repo_rename.config import load_rules
from repo_rename.errors import ConfigError


def test_loads_rules_in_order(tmp_path: Path) -> None:
    path = tmp_path / "renames.json"
    path.write_text('[{"old": "training", "new": "hello"}, {"old": "a", "new": "b"}]')
    assert list(load_rules(path).items()) == [("training", "hello"), ("a", "b")]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json", "Invalid JSON"),
        ('{"old": "a", "new": "b"}', "should be a valid array"),
        ("[]", "at least 1 item"),
        ('[{"old": "a"}]', "0.new: Field required"),
        ('[{"old": "", "new": "b"}]', "at least 1 character"),
        ('[{"old": "a", "new": "b", "typo": 1}]', "Extra inputs"),
        ('[{"old": "a", "new": "a"}]', "are both 'a'"),
        ('[{"old": "a", "new": "b"}, {"old": "a", "new": "c"}]', "duplicate 'old' names: 'a'"),
    ],
)
def test_rejects_invalid_files(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "renames.json"
    path.write_text(content)
    with pytest.raises(ConfigError, match=message):
        load_rules(path)


def test_reports_a_file_that_cannot_be_read(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"cannot read .*missing\.json: No such file"):
        load_rules(tmp_path / "missing.json")

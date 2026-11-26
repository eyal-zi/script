import subprocess
from pathlib import Path

import pytest

from repo_rename.errors import GitError
from repo_rename.git import list_files


def test_lists_a_conflicted_file_once(repo: Path) -> None:
    (repo / "a.txt").write_text("base\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "other")
    (repo / "a.txt").write_text("other\n")
    _git(repo, "commit", "-qam", "other")
    _git(repo, "checkout", "-q", "-")
    (repo / "a.txt").write_text("main\n")
    _git(repo, "commit", "-qam", "main")
    _git(repo, "merge", "other", check=False)  # conflicts: git lists a.txt once per stage

    assert list_files(repo) == [Path("a.txt")]


def test_reports_gits_own_message(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitError, match=r"^not a git repository"):
        list_files(plain)


def test_reports_a_missing_git_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    with pytest.raises(GitError, match="git executable not found on PATH"):
        list_files(tmp_path)


def _git(repo: Path, *args: str, check: bool = True) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "-C", str(repo), *identity, *args], check=check, capture_output=True)

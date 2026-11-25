"""End-to-end tests: run the CLI against real git repositories."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from repo_rename import contents
from repo_rename.cli import ExitCode, app

runner = CliRunner()

# The platform check comes first: os.geteuid doesn't exist on Windows.
_needs_file_permissions = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="file permissions only restrict non-root users on POSIX systems",
)


def test_renames_contents_files_and_directories(repo: Path) -> None:
    _write(
        repo,
        {
            "src/training/training_job.py": "class TrainingJob:\n    TRAINING_DIR = 'trainings'\n",
            "docs/Training.md": "Run training-job before pretraining.\n",
            "README.md": "unrelated\n",
        },
    )
    _git(repo, "add", "src")  # a mix of tracked and untracked files

    _run(repo, {"training": "hello"})

    assert _tree(repo) == {
        "src/hello/hello_job.py": b"class HelloJob:\n    HELLO_DIR = 'hellos'\n",
        "docs/Hello.md": b"Run hello-job before prehello.\n",
        "README.md": b"unrelated\n",
    }


def test_renames_every_case_style(repo: Path) -> None:
    _write(repo, {"app.py": "data_loader = DataLoader(DATA_LOADER_SIZE)  # dataLoader\n"})
    _run(repo, {"data_loader": "batch_reader"})
    assert (repo / "app.py").read_text() == (
        "batch_reader = BatchReader(BATCH_READER_SIZE)  # batchReader\n"
    )


def test_exact_renames_only_the_given_spelling(repo: Path) -> None:
    _write(repo, {"a.txt": "training Training TRAINING\n"})
    _run(repo, {"training": "hello"}, "--exact")
    assert (repo / "a.txt").read_text() == "hello Training TRAINING\n"


def test_never_touches_the_git_directory(repo: Path) -> None:
    _write(repo, {"training.py": "training = 1\n"})
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "training")
    _git(repo, "branch", "training")
    git_dir_before = _tree(repo / ".git")

    _run(repo, {"training": "hello"})

    assert _tree(repo / ".git") == git_dir_before
    assert (repo / "hello.py").read_text() == "hello = 1\n"


def test_ignored_files_are_skipped_unless_requested(repo: Path) -> None:
    _write(repo, {".gitignore": "build/\n", "build/training.txt": "training\n"})
    _run(repo, {"training": "hello"})
    assert (repo / "build/training.txt").read_text() == "training\n"

    _run(repo, {"training": "hello"}, "--include-ignored")
    assert (repo / "build/hello.txt").read_text() == "hello\n"


def test_excluded_pathspecs_are_left_alone(repo: Path) -> None:
    _write(repo, {"vendor/training.txt": "training", "CHANGES.md": "training", "a.txt": "training"})
    _run(repo, {"training": "hello"}, "--exclude", "vendor", "-e", "*.md")
    assert _tree(repo) == {
        "vendor/training.txt": b"training",
        "CHANGES.md": b"training",
        "a.txt": b"hello",
    }


def test_binary_files_are_renamed_but_not_rewritten(repo: Path) -> None:
    _write(repo, {"training.bin": b"\0training\0"})
    result = _run(repo, {"training": "hello"})
    assert _tree(repo) == {"hello.bin": b"\0training\0"}
    assert "alone, still containing old names:\n  training.bin (1, binary)" in result.stdout


def test_symlink_targets_follow_the_renames(repo: Path) -> None:
    _write(repo, {"training/data.txt": "data\n"})
    (repo / "link").symlink_to("training/data.txt")
    _run(repo, {"training": "hello"})
    assert os.readlink(repo / "link") == "hello/data.txt"  # noqa: PTH115
    assert (repo / "link").read_text() == "data\n"


def test_renames_file_inside_the_repo_is_left_alone(repo: Path) -> None:
    config = repo / "renames.json"
    config.write_text('[{"old": "training", "new": "hello"}]')
    original_config = config.read_bytes()
    _write(repo, {"a.txt": "training"})

    result = runner.invoke(app, [str(repo), "--renames", str(config)])

    assert result.exit_code == ExitCode.SUCCESS, result.output
    assert _tree(repo) == {"renames.json": original_config, "a.txt": b"hello"}


def test_dry_run_reports_but_changes_nothing(repo: Path) -> None:
    _write(repo, {"training/a.py": "training\n"})
    before = _tree(repo)

    result = _run(repo, {"training": "hello"}, "--dry-run")

    assert _tree(repo) == before
    assert "training/a.py (1)" in result.stdout
    assert "training → hello" in result.stdout


def test_conflicting_rename_aborts_before_changing_anything(repo: Path) -> None:
    _write(repo, {"training.py": "training\n", "hello.py": "hello\n"})
    before = _tree(repo)

    result = _run(repo, {"training": "hello"}, expected_exit=ExitCode.INVALID_INPUT)

    assert "hello.py already exists" in result.stderr
    assert _tree(repo) == before


def test_rejects_a_directory_outside_git(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    result = _run(plain, {"training": "hello"}, expected_exit=ExitCode.INVALID_INPUT)
    assert "not a git repository" in result.stderr


def test_rejects_an_invalid_renames_file(repo: Path) -> None:
    result = _run(repo, {"same": "same"}, expected_exit=ExitCode.INVALID_INPUT)
    assert "are both 'same'" in result.stderr


@_needs_file_permissions
def test_unreadable_files_are_reported_and_the_rest_still_renamed(repo: Path) -> None:
    _write(repo, {"a.txt": "training", "locked.txt": "training"})
    (repo / "locked.txt").chmod(0)

    result = _run(repo, {"training": "hello"}, expected_exit=ExitCode.PARTIAL_FAILURE)

    assert "Failed: locked.txt" in result.stderr
    assert (repo / "a.txt").read_text() == "hello"


@_needs_file_permissions
def test_failed_path_rename_is_reported(repo: Path) -> None:
    _write(repo, {"locked/training.txt": "unrelated"})
    (repo / "locked").chmod(0o555)  # its entries can't be renamed
    try:
        result = _run(repo, {"training": "hello"}, expected_exit=ExitCode.PARTIAL_FAILURE)
    finally:
        (repo / "locked").chmod(0o755)

    assert "renaming paths failed" in result.stderr


def test_parallel_run_rewrites_every_file(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Tiny chunks, so these 10 files really are split across the 4 worker processes.
    monkeypatch.setattr(contents, "_CHUNK_SIZE", 2)
    _write(repo, {f"pkg/training_{i}.py": f"training = {i}\n" for i in range(10)})
    _run(repo, {"training": "hello"}, "--jobs", "4")
    assert _tree(repo) == {f"pkg/hello_{i}.py": f"hello = {i}\n".encode() for i in range(10)}


def _run(
    repo: Path,
    rules: dict[str, str],
    *options: str,
    expected_exit: ExitCode = ExitCode.SUCCESS,
) -> Result:
    """Run the CLI on `repo` with `rules`, checking its exit code (showing its output if wrong)."""
    config = repo.parent / "renames.json"
    config.write_text(json.dumps([{"old": old, "new": new} for old, new in rules.items()]))
    result = runner.invoke(app, [str(repo), "--renames", str(config), *options])
    assert result.exit_code == expected_exit, result.output
    return result


def _write(root: Path, files: dict[str, str] | dict[str, bytes]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under `root` (outside .git) with its contents; symlinks as their target."""
    return {
        path.relative_to(root).as_posix(): (
            os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()  # noqa: PTH115
        )
        for path in root.rglob("*")
        if (path.is_symlink() or path.is_file()) and ".git" not in path.relative_to(root).parts
    }


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

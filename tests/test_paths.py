from pathlib import Path

import pytest

from repo_rename.errors import PathRenameError
from repo_rename.paths import PathRename, apply_renames, plan_renames
from repo_rename.replacer import Replacer

REPLACER = Replacer({"training": "hello"})


def _touch(root: Path, *names: str) -> list[Path]:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).touch()
    return [Path(name) for name in names]


def test_plans_deepest_paths_first_with_final_targets(tmp_path: Path) -> None:
    files = _touch(tmp_path, "training/training.py", "training/other.py", "docs/a.md")
    assert plan_renames(tmp_path, files, REPLACER) == [
        PathRename(Path("training/training.py"), Path("hello/hello.py")),
        PathRename(Path("training"), Path("hello")),
    ]


def test_applying_the_plan_moves_everything(tmp_path: Path) -> None:
    files = _touch(tmp_path, "a/training/training.py", "a/training/other.py")
    apply_renames(tmp_path, plan_renames(tmp_path, files, REPLACER))
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.py")) == [
        "a/hello/hello.py",
        "a/hello/other.py",
    ]


def test_existing_destination_is_a_conflict(tmp_path: Path) -> None:
    files = _touch(tmp_path, "training.py", "hello.py")
    with pytest.raises(PathRenameError, match=r"hello\.py already exists"):
        plan_renames(tmp_path, files, REPLACER)


def test_two_paths_renamed_to_the_same_name_conflict(tmp_path: Path) -> None:
    files = _touch(tmp_path, "foo.py", "bar.py")
    with pytest.raises(PathRenameError, match=r"would both be renamed to baz\.py"):
        plan_renames(tmp_path, files, Replacer({"foo": "baz", "bar": "baz"}))


def test_invalid_new_name_is_rejected(tmp_path: Path) -> None:
    files = _touch(tmp_path, "training")
    with pytest.raises(PathRenameError, match="'a/b' is not a valid name"):
        plan_renames(tmp_path, files, Replacer({"training": "a/b"}))


def test_submodules_are_not_renamed(tmp_path: Path) -> None:
    (tmp_path / "training").mkdir()  # git lists a submodule as if it were a file
    assert plan_renames(tmp_path, [Path("training")], REPLACER) == []


def test_deleted_files_are_not_renamed(tmp_path: Path) -> None:
    # git still lists a tracked file after it's deleted from the work tree
    assert plan_renames(tmp_path, [Path("training.py")], REPLACER) == []

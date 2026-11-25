"""Plan and apply renames of files and directories whose names contain an old name."""

import os
import stat
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from repo_rename.errors import PathRenameError
from repo_rename.replacer import Replacer

_FORBIDDEN_NAME_CHARS = frozenset(f"\0/{os.sep}{os.altsep or ''}")


@dataclass(frozen=True, slots=True)
class PathRename:
    """A file or directory whose own name changes. Paths are relative to the repo.

    `final_path` is where it ends up once its parent directories are renamed too.
    """

    source: Path
    final_path: Path

    @property
    def destination(self) -> Path:
        """`source` with only its last component renamed: the single move to perform."""
        return self.source.with_name(self.final_path.name)


def plan_renames(root: Path, files: Collection[Path], replacer: Replacer) -> list[PathRename]:
    """Plan renames for `files` and for every directory that contains them.

    The plan lists the deepest paths first, so every move happens while its parent
    directory still has its old name. Raises PathRenameError, before anything is
    touched, if a rename would overwrite an existing path or create an invalid name.
    """
    directories = _parent_directories(files)
    new_names = _new_names({*files, *directories}, replacer)
    renames: list[PathRename] = []
    problems: list[str] = []
    for path in sorted(new_names, key=_deepest_first):
        if not _exists_as(root / path, directory=path in directories):
            continue
        if _is_valid_name(new_names[path]):
            renames.append(PathRename(path, _rename_every_part(path, replacer)))
        else:
            problems.append(f"cannot rename {path}: {new_names[path]!r} is not a valid name")

    problems += _collision_problems(root, renames)
    if problems:
        raise PathRenameError(problems)
    return renames


def apply_renames(root: Path, renames: Iterable[PathRename]) -> None:
    """Perform the moves of a plan made by `plan_renames`, in its order."""
    for rename in renames:
        (root / rename.source).rename(root / rename.destination)


def _parent_directories(files: Iterable[Path]) -> set[Path]:
    """Every directory containing one of `files`, except the root itself."""
    directories: set[Path] = set()
    for file in files:
        for parent in file.parents:
            if parent in directories:
                break  # so are all of its ancestors
            directories.add(parent)
    directories.discard(Path())
    return directories


def _new_names(paths: Iterable[Path], replacer: Replacer) -> dict[Path, str]:
    """Map each path whose own name contains an old name to its new name."""
    new_names = {}
    for path in paths:
        new_name, count = replacer.replace_str(path.name)
        if count:
            new_names[path] = new_name
    return new_names


def _collision_problems(root: Path, renames: Iterable[PathRename]) -> list[str]:
    problems = []
    claimed: dict[Path, Path] = {}  # destination -> the source moving there
    for rename in renames:
        if rename.destination in claimed:
            problems.append(
                f"{claimed[rename.destination]} and {rename.source}"
                f" would both be renamed to {rename.destination}"
            )
            continue
        claimed[rename.destination] = rename.source
        if _is_taken(root / rename.destination, other_than=root / rename.source):
            problems.append(f"cannot rename {rename.source}: {rename.destination} already exists")
    return problems


def _is_taken(path: Path, *, other_than: Path) -> bool:
    """Whether something other than `other_than` exists at `path`.

    On case-insensitive file systems, the destination of a case-only rename *is* `other_than`.
    """
    try:
        return not os.path.samestat(path.lstat(), other_than.lstat())
    except FileNotFoundError:
        return False


def _exists_as(path: Path, *, directory: bool) -> bool:
    """Whether `path` exists and is a directory exactly when expected.

    Git lists submodules and nested repositories as if they were files; those are
    real directories on disk and are left alone.
    """
    try:
        return stat.S_ISDIR(path.lstat().st_mode) == directory
    except FileNotFoundError:
        return False  # tracked by git but deleted from the work tree


def _rename_every_part(path: Path, replacer: Replacer) -> Path:
    return Path(*(replacer.replace_str(part)[0] for part in path.parts))


def _is_valid_name(name: str) -> bool:
    return name not in {"", ".", ".."} and _FORBIDDEN_NAME_CHARS.isdisjoint(name)


def _deepest_first(path: Path) -> tuple[int, Path]:
    return -len(path.parts), path

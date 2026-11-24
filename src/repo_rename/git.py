"""List the files of a git work tree. Nothing inside ``.git`` is ever returned."""

import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

from repo_rename.errors import GitError

_GIT_DIR = ".git"


def list_files(
    root: Path, *, include_ignored: bool = False, exclude: Iterable[str] = ()
) -> list[Path]:
    """Return the tracked and untracked files under `root`, relative to it.

    Files ignored by git (.gitignore and friends) are left out unless
    `include_ignored` is set. `exclude` takes git pathspecs such as ``vendor`` or
    ``*.lock`` to leave out as well.
    """
    command = ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others"]
    if not include_ignored:
        command.append("--exclude-standard")
    command += ["--", ".", *(f":(exclude){pattern}" for pattern in exclude)]

    # dict.fromkeys drops duplicates (git lists conflicted files once per merge stage).
    entries = dict.fromkeys(_run(command).split(b"\0"))
    paths = (Path(os.fsdecode(entry)) for entry in entries if entry)
    return [path for path in paths if _GIT_DIR not in path.parts]


def _run(command: list[str]) -> bytes:
    try:
        result = subprocess.run(command, capture_output=True, check=True)
    except FileNotFoundError:
        raise GitError("git executable not found on PATH") from None
    except subprocess.CalledProcessError as error:
        raise GitError(error.stderr.decode(errors="replace").strip()) from None
    return result.stdout

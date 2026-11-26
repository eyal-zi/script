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
    args = ["ls-files", "-z", "--cached", "--others"]
    if not include_ignored:
        args.append("--exclude-standard")
    args += ["--", ".", *(f":(exclude){pattern}" for pattern in exclude)]

    # dict.fromkeys drops duplicates (git lists conflicted files once per merge stage).
    entries = dict.fromkeys(_run_git(root, *args).split(b"\0"))
    paths = (Path(os.fsdecode(entry)) for entry in entries if entry)
    return [path for path in paths if _GIT_DIR not in path.parts]


def _run_git(root: Path, *args: str) -> bytes:
    """Run ``git -C root ARGS`` and return its output. Raises GitError."""
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    except FileNotFoundError as error:
        raise GitError("git executable not found on PATH") from error
    except subprocess.CalledProcessError as error:
        # The CLI already says "Error: ", so git's own "fatal: " would repeat it.
        message = error.stderr.decode(errors="replace").strip().removeprefix("fatal: ")
        raise GitError(message or f"git exited with status {error.returncode}") from error
    return result.stdout

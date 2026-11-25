"""Rewrite file contents (and symlink targets), spread over worker processes."""

import math
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from repo_rename.replacer import Replacer

# Same heuristic as git: a NUL byte near the start of a file means it's binary.
_BINARY_SNIFF_BYTES = 8000
# Files handed to a worker at a time; large enough to amortize inter-process overhead.
_CHUNK_SIZE = 64


class SkipReason(Enum):
    """Why a file's contents were left alone."""

    BINARY = "binary"
    NOT_A_REGULAR_FILE = "not a regular file"  # e.g. a submodule or nested repository
    MISSING = "missing"  # tracked by git but deleted from the work tree


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """What happened to one file.

    `matches` counts the old names found in it. They were replaced unless it's a dry
    run or the file was `skipped`. `error` says why the file couldn't be processed.
    """

    path: Path
    matches: int = 0
    skipped: SkipReason | None = None
    error: str | None = None


def iter_rewrites(
    root: Path,
    paths: Sequence[Path],
    replacer: Replacer,
    *,
    dry_run: bool = False,
    jobs: int = 1,
) -> Iterator[RewriteResult]:
    """Rewrite each file in `paths` (relative to `root`), yielding the results in order.

    Lazy: nothing is read or written until the results are consumed. Uses up to `jobs`
    processes. With `dry_run`, matches are counted but not written.
    """
    rewriter = _Rewriter(root, replacer, dry_run=dry_run)
    workers = min(jobs, math.ceil(len(paths) / _CHUNK_SIZE))
    if workers <= 1:
        yield from map(rewriter, paths)
        return
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(rewriter,)) as pool:
        yield from pool.map(_rewrite_in_worker, paths, chunksize=_CHUNK_SIZE)


@dataclass(frozen=True, slots=True)
class _Rewriter:
    """Rewrites one repo-relative path; picklable, so it can be sent to workers."""

    root: Path
    replacer: Replacer
    dry_run: bool

    def __call__(self, path: Path) -> RewriteResult:
        try:
            return self._rewrite(path)
        except OSError as error:
            return RewriteResult(path, error=error.strerror or str(error))

    def _rewrite(self, path: Path) -> RewriteResult:
        """Replace matches in a file, or in a symlink's target. Raises OSError."""
        absolute = self.root / path
        try:
            mode = absolute.lstat().st_mode
        except FileNotFoundError:
            return RewriteResult(path, skipped=SkipReason.MISSING)
        if stat.S_ISLNK(mode):
            matches = _rewrite_symlink(absolute, self.replacer, dry_run=self.dry_run)
            return RewriteResult(path, matches=matches)
        if not stat.S_ISREG(mode):
            return RewriteResult(path, skipped=SkipReason.NOT_A_REGULAR_FILE)

        data = absolute.read_bytes()
        # Count the matches in binary files too: the report lists them as left alone.
        new_data, matches = self.replacer.replace(data)
        if _is_binary(data):
            return RewriteResult(path, matches=matches, skipped=SkipReason.BINARY)
        if matches and not self.dry_run:
            _atomic_write(absolute, new_data)
        return RewriteResult(path, matches=matches)


# Each worker process receives the rewriter (and its possibly large replacement
# table) once at startup, instead of once per chunk of files.
_worker_rewriter: _Rewriter | None = None


def _init_worker(rewriter: _Rewriter) -> None:
    global _worker_rewriter  # noqa: PLW0603
    _worker_rewriter = rewriter


def _rewrite_in_worker(path: Path) -> RewriteResult:
    assert _worker_rewriter is not None, "worker process was not initialized"
    return _worker_rewriter(path)


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:_BINARY_SNIFF_BYTES]


def _rewrite_symlink(link: Path, replacer: Replacer, *, dry_run: bool) -> int:
    """Point a symlink at the renamed target, so it still resolves after the renames.

    Returns the number of matches in the target.
    """
    # Not Path.readlink(): it normalizes the target ("./a/" -> "a"), changing the link.
    target, matches = replacer.replace_str(os.readlink(link))  # noqa: PTH115
    if matches and not dry_run:
        # tempfile can't create symlinks, so make up an unused sibling name instead.
        temporary = link.with_name(f".{link.name}.{uuid.uuid4().hex}.tmp")
        temporary.symlink_to(target)
        with _removed_on_error(temporary):
            temporary.replace(link)
    return matches


def _atomic_write(path: Path, data: bytes) -> None:
    """Overwrite `path` through a temporary file, so it's never left half-written."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    with _removed_on_error(temporary):
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        shutil.copymode(path, temporary)
        temporary.replace(path)


@contextmanager
def _removed_on_error(temporary: Path) -> Iterator[None]:
    """Delete `temporary` if the block raises, so no stray files are left behind."""
    try:
        yield
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

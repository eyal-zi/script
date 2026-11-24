"""Rewrite file contents (and symlink targets), spread over worker processes."""

import math
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from repo_rename.replacer import Replacer

# Same heuristic as git: a NUL byte near the start of a file means it's binary.
_BINARY_SNIFF_BYTES = 8000
# Files handed to a worker at a time; large enough to amortize inter-process overhead.
_CHUNK_SIZE = 64


@dataclass(frozen=True, slots=True)
class RewriteResult:
    """What happened to one file: how many replacements were made, or why it failed."""

    path: Path
    replacements: int = 0
    error: str | None = None


def rewrite_files(
    root: Path,
    paths: Sequence[Path],
    replacer: Replacer,
    *,
    dry_run: bool = False,
    jobs: int = 1,
) -> Iterator[RewriteResult]:
    """Rewrite every file in `paths` (relative to `root`), yielding results in order.

    Uses up to `jobs` processes. With `dry_run`, matches are counted but not written.
    """
    rewriter = _Rewriter(root, replacer, dry_run)
    workers = min(jobs, math.ceil(len(paths) / _CHUNK_SIZE))
    if workers <= 1:
        yield from map(rewriter, paths)
        return
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(rewriter,)) as pool:
        yield from pool.map(_rewrite_in_worker, paths, chunksize=_CHUNK_SIZE)


def rewrite_file(path: Path, replacer: Replacer, *, dry_run: bool = False) -> int:
    """Replace matches in a file, or in a symlink's target, and return how many.

    Binary files, directories (such as submodules) and missing files are skipped.
    """
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return 0  # tracked by git but deleted from the work tree
    if stat.S_ISLNK(mode):
        return _rewrite_symlink(path, replacer, dry_run=dry_run)
    if not stat.S_ISREG(mode):
        return 0

    data = path.read_bytes()
    if _is_binary(data):
        return 0
    new_data, count = replacer.replace(data)
    if count and not dry_run:
        _atomic_write(path, new_data)
    return count


@dataclass(frozen=True, slots=True)
class _Rewriter:
    """Rewrites one repo-relative path; picklable, so it can be sent to workers."""

    root: Path
    replacer: Replacer
    dry_run: bool

    def __call__(self, path: Path) -> RewriteResult:
        try:
            count = rewrite_file(self.root / path, self.replacer, dry_run=self.dry_run)
        except OSError as error:
            return RewriteResult(path, error=error.strerror or str(error))
        return RewriteResult(path, count)


# Each worker process receives the rewriter (and its possibly large replacement
# table) once at startup, instead of once per chunk of files.
_worker_rewriter: _Rewriter | None = None


def _init_worker(rewriter: _Rewriter) -> None:
    global _worker_rewriter
    _worker_rewriter = rewriter


def _rewrite_in_worker(path: Path) -> RewriteResult:
    assert _worker_rewriter is not None, "worker process was not initialized"
    return _worker_rewriter(path)


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:_BINARY_SNIFF_BYTES]


def _rewrite_symlink(link: Path, replacer: Replacer, *, dry_run: bool) -> int:
    """Point a symlink at the renamed target, so it still resolves after the renames."""
    target, count = replacer.replace_str(os.readlink(link))
    if count and not dry_run:
        temporary = link.with_name(f".{link.name}.{uuid.uuid4().hex}.tmp")
        temporary.symlink_to(target)
        _replace(temporary, link)
    return count


def _atomic_write(path: Path, data: bytes) -> None:
    """Overwrite `path` through a temporary file, so it's never left half-written."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        shutil.copymode(path, temporary)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    _replace(temporary, path)


def _replace(temporary: Path, path: Path) -> None:
    """Atomically move `temporary` over `path`, cleaning up if that fails."""
    try:
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

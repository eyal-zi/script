"""Errors the user can fix. The CLI reports them without a traceback."""

from collections.abc import Iterable


class RepoRenameError(Exception):
    """Base class for all expected errors."""


class ConfigError(RepoRenameError):
    """The renames file can't be read or is invalid."""


class GitError(RepoRenameError):
    """A git command failed, e.g. because the path isn't inside a git work tree."""


class PathConflictError(RepoRenameError):
    """Renaming files or directories would overwrite paths or create invalid names."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = list(problems)
        details = "\n".join(f"  {problem}" for problem in self.problems)
        super().__init__(f"cannot rename paths:\n{details}")

"""Errors the user can fix. The CLI reports them without a traceback."""

from collections.abc import Iterable


class RepoRenameError(Exception):
    """Base class for all expected errors: a message, then any problems one per line."""

    def __init__(self, message: str, problems: Iterable[str] = ()) -> None:
        self.problems = list(problems)
        super().__init__(message + "".join(f"\n  {problem}" for problem in self.problems))


class ConfigError(RepoRenameError):
    """The rules file can't be read or is invalid."""


class GitError(RepoRenameError):
    """A git command failed, e.g. because the path isn't inside a git work tree."""


class PathRenameError(RepoRenameError):
    """Renaming files or directories would overwrite paths or create invalid names."""

    def __init__(self, problems: Iterable[str]) -> None:
        super().__init__("cannot rename paths:", problems)


def os_error_reason(error: OSError) -> str:
    """What went wrong, without the paths involved: e.g. ``Permission denied``."""
    return error.strerror or str(error)

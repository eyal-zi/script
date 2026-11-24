from collections.abc import Iterable

from repo_rename.errors.repo_rename_error import RepoRenameError


class PathConflictError(RepoRenameError):
    """Renaming files or directories would overwrite paths or create invalid names."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = list(problems)
        details = "\n".join(f"  {problem}" for problem in self.problems)
        super().__init__(f"cannot rename paths:\n{details}")

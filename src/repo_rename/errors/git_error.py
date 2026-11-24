from repo_rename.errors.repo_rename_error import RepoRenameError


class GitError(RepoRenameError):
    """A git command failed, e.g. because the path isn't inside a git work tree."""

from repo_rename.errors.repo_rename_error import RepoRenameError


class ConfigError(RepoRenameError):
    """The renames file can't be read or is invalid."""

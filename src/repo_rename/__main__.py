"""Allow running the tool as ``python -m repo_rename``."""

from repo_rename.cli import app

if __name__ == "__main__":
    app(prog_name="repo-rename")

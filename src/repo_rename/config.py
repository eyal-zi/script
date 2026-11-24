"""Load and validate the renames file: a JSON array of ``{"old": ..., "new": ...}`` objects."""

from collections import Counter
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, model_validator

from repo_rename.errors import ConfigError

NonEmptyStr = Annotated[str, Field(min_length=1)]


class Rename(BaseModel):
    """A single rule: replace every occurrence of `old` with `new`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    old: NonEmptyStr
    new: NonEmptyStr

    @model_validator(mode="after")
    def _old_differs_from_new(self) -> "Rename":
        if self.old == self.new:
            raise ValueError(f"'old' and 'new' are both {self.old!r}")
        return self


class RenameList(RootModel[list[Rename]]):
    """The whole file: at least one rule, each `old` name appearing once."""

    root: Annotated[list[Rename], Field(min_length=1)]

    @model_validator(mode="after")
    def _old_names_are_unique(self) -> "RenameList":
        counts = Counter(rename.old for rename in self.root)
        if duplicates := [old for old, count in counts.items() if count > 1]:
            raise ValueError(f"duplicate 'old' names: {', '.join(map(repr, duplicates))}")
        return self


def load_renames(path: Path) -> dict[str, str]:
    """Read the renames file and return its rules as an ordered ``{old: new}`` mapping."""
    try:
        rules = RenameList.model_validate_json(path.read_bytes()).root
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from error
    except ValidationError as error:
        raise ConfigError(f"invalid {path.name}:\n{_describe(error)}") from None
    return {rule.old: rule.new for rule in rules}


def _describe(error: ValidationError) -> str:
    """Format validation issues one per line, e.g. ``  0.new: Field required``."""
    return "\n".join(
        f"  {'.'.join(map(str, issue['loc'])) or '<root>'}: {issue['msg']}"
        for issue in error.errors(include_url=False)
    )

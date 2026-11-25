"""Load and validate the rules file: a JSON array of ``{"old": ..., "new": ...}`` objects."""

from collections import Counter
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, model_validator

from repo_rename.errors import ConfigError

_NonEmptyStr = Annotated[str, Field(min_length=1)]


class Rule(BaseModel):
    """Replace every occurrence of `old` with `new`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    old: _NonEmptyStr
    new: _NonEmptyStr

    @model_validator(mode="after")
    def _old_differs_from_new(self) -> "Rule":
        if self.old == self.new:
            raise ValueError(f"'old' and 'new' are both {self.old!r}")
        return self


class RuleList(RootModel[list[Rule]]):
    """The whole rules file: at least one rule, each `old` name appearing once."""

    root: Annotated[list[Rule], Field(min_length=1)]

    @model_validator(mode="after")
    def _old_names_are_unique(self) -> "RuleList":
        counts = Counter(rule.old for rule in self.root)
        if duplicates := [old for old, count in counts.items() if count > 1]:
            raise ValueError(f"duplicate 'old' names: {', '.join(map(repr, duplicates))}")
        return self


def load_rules(path: Path) -> dict[str, str]:
    """Read the rules file and return it as an ordered ``{old: new}`` mapping."""
    try:
        rules = RuleList.model_validate_json(path.read_bytes()).root
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror}") from error
    except ValidationError as error:
        raise ConfigError(f"invalid {path}:\n{_format_issues(error)}") from None
    return {rule.old: rule.new for rule in rules}


def _format_issues(error: ValidationError) -> str:
    """Format validation issues one per line, e.g. ``  0.new: Field required``."""
    return "\n".join(
        f"  {'.'.join(map(str, issue['loc'])) or '<root>'}: {issue['msg']}"
        for issue in error.errors(include_url=False)
    )

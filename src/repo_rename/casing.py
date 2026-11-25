"""Spell each rename in every common case style.

A rule like ``data_loader -> batch_reader`` should also turn ``DataLoader`` into
``BatchReader``, ``DATA_LOADER`` into ``BATCH_READER``, ``data-loader`` into
``batch-reader`` and so on. This module derives those extra pairs.
"""

import re
from collections.abc import Callable, Iterator, Mapping

# Letters and digits, optionally joined by single "_", "-" or " ". Other names (with
# dots, slashes, leading underscores, ...) are only ever renamed exactly as written.
_IDENTIFIER = re.compile(r"[A-Za-z0-9]+(?:[_\- ][A-Za-z0-9]+)*")
# Word boundaries inside camelCase and PascalCase, e.g. "dataLoader", "HTTPServer".
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATOR = re.compile(r"[_\- ]")

# Order matters: when several styles spell the old name identically (always true for
# one-word names), the first of them decides how the new name is spelled.
_CASE_STYLES: Mapping[str, Callable[[list[str]], str]] = {
    "snake_case": lambda words: "_".join(words),
    "SCREAMING_SNAKE_CASE": lambda words: "_".join(words).upper(),
    "camelCase": lambda words: words[0] + "".join(word.capitalize() for word in words[1:]),
    "PascalCase": lambda words: "".join(word.capitalize() for word in words),
    "kebab-case": lambda words: "-".join(words),
    "SCREAMING-KEBAB-CASE": lambda words: "-".join(words).upper(),
    "Train-Case": lambda words: "-".join(word.capitalize() for word in words),
    "lower words": lambda words: " ".join(words),
    "Title Words": lambda words: " ".join(word.capitalize() for word in words),
    "Sentence words": lambda words: " ".join(words).capitalize(),
    "UPPER WORDS": lambda words: " ".join(words).upper(),
}


def split_words(name: str) -> list[str] | None:
    """Split an identifier-like name into lowercase words.

    "DataLoader", "dataLoader", "data_loader", "DATA-LOADER" and "data loader" all
    give ``["data", "loader"]``. Returns None for names that aren't identifier-like.
    """
    if not _IDENTIFIER.fullmatch(name):
        return None
    return _SEPARATOR.split(_CAMEL_BOUNDARY.sub(" ", name).lower())


def with_case_variants(rules: Mapping[str, str]) -> dict[str, str]:
    """Return `rules` plus each ``old -> new`` pair re-spelled in every case style.

    Explicit rules always win over generated variants, and when two rules generate
    the same spelling, the earlier rule wins.
    """
    expanded = dict(rules)
    for old, new in rules.items():
        for old_variant, new_variant in _case_variants(old, new):
            if old_variant != new_variant:
                expanded.setdefault(old_variant, new_variant)
    return expanded


def _case_variants(old: str, new: str) -> Iterator[tuple[str, str]]:
    old_words, new_words = split_words(old), split_words(new)
    if old_words is None or new_words is None:
        return
    for style in _CASE_STYLES.values():
        yield style(old_words), style(new_words)

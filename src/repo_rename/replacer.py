"""Fast, simultaneous replacement of many literal strings."""

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


class Replacer:
    """Replace many literal strings in a single pass, preferring the longest match.

    Matching is case-sensitive and ignores word boundaries, so with
    ``{"training": "hello"}`` the text "pretrainings" becomes "prehellos".
    Replacements never cascade: with ``{"a": "b", "b": "a"}``, "ab" becomes "ba".

    It works on bytes (names are encoded as UTF-8), so files in any ASCII-compatible
    encoding are handled, and every byte outside a match is kept exactly as it was.
    """

    def __init__(self, table: Mapping[str, str]) -> None:
        if not table or "" in table:
            raise ValueError("table must map non-empty strings")
        self._table = {old.encode(): new.encode() for old, new in table.items()}
        self._pattern = re.compile(_trie_regex(self._table))

    def replace(self, data: bytes) -> tuple[bytes, int]:
        """Return `data` with every match replaced, and the number of replacements."""
        return self._pattern.subn(self._substitute, data)

    def replace_str(self, text: str) -> tuple[str, int]:
        """Like `replace`, for OS strings such as file names and symlink targets."""
        data, count = self.replace(os.fsencode(text))
        return os.fsdecode(data), count

    def _substitute(self, match: re.Match[bytes]) -> bytes:
        return self._table[match[0]]


def _trie_regex(words: Iterable[bytes]) -> bytes:
    """Build a regex that matches any of `words`, longest first, shaped like a trie.

    ``{"train", "training", "trial"}`` becomes ``tr(?:ain(?:ing)?|ial)``. The cost of
    matching grows with the length of a match rather than the number of words; a plain
    ``a|b|c`` alternation gets ~100x slower once there are thousands of names.
    """
    root = _TrieNode()
    for word in words:
        node = root
        for byte in word:
            node = node.children.setdefault(byte, _TrieNode())
        node.is_word_end = True
    return root.to_regex()


@dataclass
class _TrieNode:
    children: dict[int, "_TrieNode"] = field(default_factory=dict)
    is_word_end: bool = False

    def to_regex(self) -> bytes:
        branches = [
            re.escape(bytes([byte])) + child.to_regex() for byte, child in self.children.items()
        ]
        if not branches:
            return b""
        if len(branches) == 1 and not self.is_word_end:
            return branches[0]
        group = b"(?:" + b"|".join(branches) + b")"
        # A greedy "?" tries the longer continuation before ending the word here.
        return group + b"?" if self.is_word_end else group

import random
import re

import pytest

from repo_rename.replacer import Replacer


def test_replaces_inside_longer_words() -> None:
    assert Replacer({"training": "hello"}).replace(b"pretrainings") == (b"prehellos", 1)


def test_prefers_the_longest_match() -> None:
    replacer = Replacer({"train": "fit", "training": "hello", "training_set": "corpus"})
    assert replacer.replace(b"train training training_set") == (b"fit hello corpus", 3)


def test_replacements_do_not_cascade() -> None:
    assert Replacer({"a": "b", "b": "a"}).replace(b"ab") == (b"ba", 2)


def test_keeps_every_byte_outside_matches() -> None:
    data = b"\xff\xfe training \r\n caf\xc3\xa9"
    assert Replacer({"training": "hello"}).replace(data) == (b"\xff\xfe hello \r\n caf\xc3\xa9", 1)


def test_matches_non_ascii_names() -> None:
    assert Replacer({"café": "tea"}).replace("un café".encode()) == (b"un tea", 1)


def test_replace_str() -> None:
    assert Replacer({"training": "hello"}).replace_str("training_data.csv") == ("hello_data.csv", 1)


@pytest.mark.parametrize("table", [{}, {"": "x"}])
def test_rejects_empty_tables(table: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Replacer(table)


def test_agrees_with_a_longest_first_alternation() -> None:
    rng = random.Random(0)
    words = {"".join(rng.choices("abc", k=rng.randint(1, 4))) for _ in range(40)}
    table = {word: word.upper() for word in words}
    reference = re.compile("|".join(sorted(map(re.escape, words), key=len, reverse=True)))
    replacer = Replacer(table)
    for _ in range(500):
        text = "".join(rng.choices("abcd", k=30))
        assert replacer.replace_str(text) == reference.subn(lambda m: table[m[0]], text)

import errno
import stat
from pathlib import Path
from typing import NoReturn

import pytest

from repo_rename.contents import RewriteResult, SkipReason, iter_rewrites
from repo_rename.replacer import Replacer

REPLACER = Replacer({"training": "hello"})


def _rewrite(root: Path, *names: str) -> list[RewriteResult]:
    return list(iter_rewrites(root, [Path(name) for name in names], REPLACER))


def test_rewrites_matches_and_keeps_the_file_mode(tmp_path: Path) -> None:
    mode = 0o755
    script = tmp_path / "run.sh"
    script.write_text("training\n")
    script.chmod(mode)

    assert _rewrite(tmp_path, "run.sh") == [RewriteResult(Path("run.sh"), matches=1)]
    assert script.read_text() == "hello\n"
    assert stat.S_IMODE(script.stat().st_mode) == mode


def test_skips_what_it_cannot_rewrite(tmp_path: Path) -> None:
    (tmp_path / "submodule").mkdir()  # git lists a submodule as if it were a file
    (tmp_path / "logo.bin").write_bytes(b"\0training")

    assert _rewrite(tmp_path, "deleted.txt", "submodule", "logo.bin") == [
        RewriteResult(Path("deleted.txt"), skipped=SkipReason.MISSING),
        RewriteResult(Path("submodule"), skipped=SkipReason.NOT_A_REGULAR_FILE),
        RewriteResult(Path("logo.bin"), matches=1, skipped=SkipReason.BINARY),
    ]
    assert (tmp_path / "logo.bin").read_bytes() == b"\0training"


def test_failed_write_keeps_the_original_and_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.txt").write_text("training")
    (tmp_path / "link").symlink_to("training")

    def fail(*_: object) -> NoReturn:
        raise PermissionError(errno.EACCES, "Permission denied")

    # Moving the temporary file into place is the last step of every rewrite.
    monkeypatch.setattr(Path, "replace", fail)

    assert _rewrite(tmp_path, "a.txt", "link") == [
        RewriteResult(Path("a.txt"), error="Permission denied"),
        RewriteResult(Path("link"), error="Permission denied"),
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["a.txt", "link"]
    assert (tmp_path / "a.txt").read_text() == "training"

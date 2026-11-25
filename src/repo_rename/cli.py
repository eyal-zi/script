"""Command-line interface: ``repo-rename REPO [--renames FILE] [OPTIONS]``."""

import os
from collections.abc import Iterable
from enum import IntEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.progress import track
from rich.text import Text

from repo_rename.casing import with_case_variants
from repo_rename.config import load_rules
from repo_rename.contents import RewriteResult, rewrite_files
from repo_rename.errors import RepoRenameError
from repo_rename.git import list_files
from repo_rename.paths import PathRename, apply_renames, plan_renames
from repo_rename.replacer import Replacer


class ExitCode(IntEnum):
    """The process exit statuses (documented in the README)."""

    SUCCESS = 0
    PARTIAL_FAILURE = 1  # the run went ahead, but some files or paths couldn't be changed
    INVALID_INPUT = 2  # bad rules file, not a git repo, conflicting renames: nothing changed


app = typer.Typer(add_completion=False)
out = Console(highlight=False)
err = Console(stderr=True, highlight=False)


@app.command()
def main(
    repo: Annotated[
        Path,
        typer.Argument(
            help="Git repository (or a directory inside one) to rename in.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    renames_file: Annotated[
        Path,
        typer.Option(
            "--renames",
            "-r",
            help='JSON array of {"old": ..., "new": ...} objects.',
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = Path("renames.json"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", "-n", help="Show what would change, write nothing.")
    ] = False,
    exact: Annotated[
        bool, typer.Option("--exact", help="Rename only the exact spellings, no case variants.")
    ] = False,
    include_ignored: Annotated[
        bool, typer.Option("--include-ignored", help="Also process files ignored by git.")
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude", "-e", help="Git pathspec to leave alone, e.g. 'vendor' or '*.lock'."
        ),
    ] = None,
    jobs: Annotated[
        int, typer.Option("--jobs", "-j", min=1, help="Number of worker processes.")
    ] = os.cpu_count() or 1,
) -> None:
    """Rename every occurrence of old names to new names across a git repository.

    Covers file contents, file names and directory names. Nothing inside .git is touched.
    """
    try:
        rules = load_rules(renames_file)
        replacer = Replacer(rules if exact else with_case_variants(rules))
        listed = list_files(repo, include_ignored=include_ignored, exclude=exclude or ())
        files = [file for file in listed if repo / file != renames_file]
        path_renames = plan_renames(repo, files, replacer)
    except RepoRenameError as error:
        _fail(f"{error}\nNothing was changed.", exit_code=ExitCode.INVALID_INPUT)

    results = _rewrite_contents(repo, files, replacer, dry_run=dry_run, jobs=jobs)
    if not dry_run:
        try:
            apply_renames(repo, path_renames)
        except OSError as error:
            _fail(f"renaming paths failed: {error}", exit_code=ExitCode.PARTIAL_FAILURE)

    _report(results, path_renames, dry_run=dry_run)
    if any(result.error for result in results):
        raise typer.Exit(ExitCode.PARTIAL_FAILURE)


def _rewrite_contents(
    repo: Path, files: list[Path], replacer: Replacer, *, dry_run: bool, jobs: int
) -> list[RewriteResult]:
    results = rewrite_files(repo, files, replacer, dry_run=dry_run, jobs=jobs)
    progress = track(
        results,
        total=len(files),
        description="Scanning",
        console=err,
        transient=True,
        disable=not err.is_terminal,  # no progress noise in pipes, logs and CI
    )
    return list(progress)


def _report(results: list[RewriteResult], path_renames: list[PathRename], *, dry_run: bool) -> None:
    with_matches = [result for result in results if result.replacements]
    changed = [result for result in with_matches if not result.skipped]
    left_alone = [result for result in with_matches if result.skipped]
    if changed:
        total = sum(result.replacements for result in changed)
        verb = "Would update" if dry_run else "Updated"
        title = f"{verb} {_count(len(changed), 'file')} ({_count(total, 'replacement')}):"
        _print_section(title, map(_with_replacement_count, changed))

    if left_alone:
        title = f"Left {_count(len(left_alone), 'file')} alone, still containing old names:"
        _print_section(title, map(_with_replacement_count, left_alone))

    if path_renames:
        verb = "Would rename" if dry_run else "Renamed"
        lines = (
            Text.assemble(str(rename.source), (" → ", "dim"), str(rename.target))
            for rename in sorted(path_renames, key=lambda rename: rename.source)
        )
        _print_section(f"{verb} {_count(len(path_renames), 'path')}:", lines)

    for result in results:
        if result.error:
            err.print(Text.assemble(("Failed: ", "red"), f"{result.path}: {result.error}"))

    if not (changed or path_renames):
        out.print("Nothing to rename.")
    elif dry_run:
        out.print("Dry run: nothing was written.", style="yellow")


def _with_replacement_count(result: RewriteResult) -> Text:
    """E.g. ``src/app.py (3)``, plus the skip reason (``logo.png (2, binary)``) if any."""
    details = ", ".join(filter(None, [str(result.replacements), result.skipped]))
    return Text.assemble(str(result.path), (f" ({details})", "dim"))


def _print_section(title: str, lines: Iterable[Text]) -> None:
    """Print a bold title and indented lines as one Text: much faster than line by line."""
    section = Text("\n").join([Text(title, style="bold"), *(Text("  ") + line for line in lines)])
    out.print(section, soft_wrap=True)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _fail(message: str, *, exit_code: ExitCode) -> NoReturn:
    err.print(Text.assemble(("Error: ", "bold red"), message))
    raise typer.Exit(exit_code)

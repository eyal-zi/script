# repo-rename

Rename names across a whole git repository in one go: inside files, and in file
and directory names. Nothing inside `.git` is ever modified.

## Install

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Usage

```bash
cp renames.example.json renames.json                         # then edit the rules
repo-rename path/to/repo --renames renames.json --dry-run   # preview every change
repo-rename path/to/repo --renames renames.json             # apply
```

`renames.json` (the default `--renames` path) is a JSON array of `old`/`new` pairs:

```json
[
  { "old": "training", "new": "hello" },
  { "old": "data_loader", "new": "batch_reader" }
]
```

Commit or stash your work first, so you can review the result with `git diff` / `git status`.

## How names are matched

- **Anywhere, even inside longer words**: `trainings` → `hellos`, `pretraining` → `prehello`.
- **In every case style** (turn off with `--exact`):

  | Spelling in the repo | Becomes        |
  | -------------------- | -------------- |
  | `data_loader`        | `batch_reader` |
  | `DATA_LOADER`        | `BATCH_READER` |
  | `dataLoader`         | `batchReader`  |
  | `DataLoader`         | `BatchReader`  |
  | `data-loader`        | `batch-reader` |
  | `DATA-LOADER`        | `BATCH-READER` |
  | `Data-Loader`        | `Batch-Reader` |
  | `data loader`        | `batch reader` |
  | `Data Loader`        | `Batch Reader` |
  | `Data loader`        | `Batch reader` |
  | `DATA LOADER`        | `BATCH READER` |

  One-word names get `training`, `Training` and `TRAINING`. Names with other characters
  (such as `com.example`) are only matched exactly as written.
- **In a single pass, longest match first**: `training_set` beats `training`, and rules never
  feed into each other (`a → b` plus `b → a` swaps the two).

## What gets changed

- Tracked files, plus untracked files that git doesn't ignore. Add `--include-ignored` to also
  process ignored ones (`node_modules`, build output, ...).
- File contents, file names and directory names. Directories are moved as a whole, so ignored
  files inside them (e.g. `__pycache__`) move along, but their contents aren't touched.
- Symlink targets are updated too, so links still resolve after the directories they point into
  are renamed.
- Binary files (a NUL byte in the first 8000 bytes, like git) keep their contents; only their
  names change. Binary files that still contain an old name are listed in the output.
- The renames file itself is never modified, even when it lives inside the repo.
- All renames are checked before anything is written: if one would overwrite an existing path,
  the run stops and nothing changes.

## Options

| Option                   | Default        | Description                                                  |
| ------------------------ | -------------- | ------------------------------------------------------------ |
| `-r, --renames FILE`     | `renames.json` | The rules file.                                              |
| `-n, --dry-run`          | off            | Show what would change, write nothing.                       |
| `--exact`                | off            | Only the exact spellings given, no case variants.            |
| `--include-ignored`      | off            | Also process files ignored by git.                           |
| `-e, --exclude PATHSPEC` | none           | Leave matching paths alone (`vendor`, `*.lock`). Repeatable. |
| `-j, --jobs N`           | CPU count      | Number of worker processes.                                  |

Exit codes (`ExitCode` in `cli.py`):

| Code | Meaning                                                                         |
| ---- | ------------------------------------------------------------------------------- |
| `0`  | Success.                                                                        |
| `1`  | The run went ahead, but some files couldn't be rewritten or a path rename failed. |
| `2`  | Invalid input (bad options or rules file, not a git repo, conflicting renames). Nothing is changed. |

## Development

```bash
pip install -U pip && pip install -e . --group dev
pytest
ruff check && ruff format --check
mypy
```

Source layout (`src/repo_rename/`):

| Module        | Responsibility                                                    |
| ------------- | ----------------------------------------------------------------- |
| `cli.py`      | Command-line options, wiring the steps together, output           |
| `config.py`   | Loading and validating the renames file (pydantic)                |
| `casing.py`   | Case-style variants (`DataLoader`, `DATA_LOADER`, ...)            |
| `replacer.py` | Single-pass, longest-match replacement of many strings at once    |
| `git.py`      | Listing the repo's files with `git ls-files`                      |
| `contents.py` | Rewriting file contents in parallel, with atomic writes           |
| `paths.py`    | Planning, conflict-checking and applying file/directory renames   |
| `errors.py`   | User-facing error types                                           |

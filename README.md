# symvision

[![CI](https://github.com/bbugyi200/symvision/actions/workflows/ci.yml/badge.svg)](https://github.com/bbugyi200/symvision/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/symvision.svg)](https://pypi.org/project/symvision/)
[![Python versions](https://img.shields.io/pypi/pyversions/symvision.svg)](https://pypi.org/project/symvision/)
[![License: MIT](https://img.shields.io/pypi/l/symvision.svg)](LICENSE)

`symvision` is a dependency-free symbol-visibility linter for Python. It finds public functions and classes that no
production code uses, private symbols imported across module boundaries, and private symbols unused in their defining
module.

Python does not enforce public and private APIs. Over time, that can leave a project with dead public surfaces and
underscore-prefixed helpers that are private in name only. `symvision` turns those conventions into an automated check
while accounting for entry points, non-Python consumers, external repositories, and APIs being built under an active
epic.

## Quick start

Install the `symvision` command with [uv](https://docs.astral.sh/uv/):

```console
uv tool install symvision
```

Or install it with pipx or pip:

```console
pipx install symvision
# or, inside a virtual environment
python -m pip install symvision
```

Scan the package definitions under `src/`:

```console
symvision src
```

`symvision` treats Python files under the requested directory as the definition tree. When the tree is inside a Git
repository, imports from tracked Python files outside it also count as usage. Definitions and imports in test-support
paths (`test/`, `tests/`, `testing/`, or `test_*.py`) do not keep production APIs alive. Functions referenced by
`[project.scripts]`, `[project.gui-scripts]`, or `[project.entry-points.*]` in the nearest `pyproject.toml` are treated
as used.

## Usage

```text
symvision [-h] [--exclude-file PATH] [--epic-symbol EPIC(SYMBOL)]
          [--exclude-decorator NAME] [-E PATH]
          DIRECTORY
```

The options that accept values may be repeated:

| Option | Meaning |
| --- | --- |
| `DIRECTORY` | Recursively scan Python definitions under this directory |
| `--exclude-file PATH` | Exclude a file from definition and usage analysis; paths are resolved from the current working directory |
| `--exclude-decorator NAME` | Ignore top-level functions and classes decorated with this name |
| `--epic-symbol EPIC(SYMBOL)` | Temporarily allow an otherwise-unused public symbol while its epic is open |
| `-E PATH`, `--external-repo-path PATH` | Add a local checkout candidate for resolving an external-repository pragma |
| `-h`, `--help` | Show command help |

For example:

```console
symvision \
  --exclude-file src/pkg/generated.py \
  --exclude-decorator register \
  src/pkg
```

## Pragmas for non-Python consumers

A pragma immediately above a top-level public function or class records a real consumer that static Python import
analysis cannot see. The target must genuinely reference the symbol; stale or unnecessary pragmas are errors.

### Local path form

Use a Git-root-relative path for generated configuration, shell code, or another non-Python consumer:

```python
# symvision: config/application.toml
def build_application() -> Application:
    ...
```

The referenced file must exist, must contain the symbol name, and must not be under `src/`. Test-support paths and
Markdown files are rejected because tests and documentation alone are not production consumers.

### External repository form

Use a Git remote URI when another repository consumes the API:

```python
# symvision: https://github.com/example/application.git
class ApplicationPlugin:
    ...
```

HTTPS, SSH URLs, scp-style Git remotes such as `git@github.com:owner/repo.git`, and `file://` URLs are supported.
Equivalent HTTPS and SSH origins are matched after normalization. Only Git-tracked, non-test files in the resolved
checkout count; both Python imports and symbol references in non-Python text files are recognized.

External repositories resolve in this order:

1. Paths passed with `--external-repo-path`, followed by paths from `SYMVISION_EXTERNAL_REPO_PATHS`.
2. The current repository's parent directory and sibling directories. A checkout named exactly for the repository is
   preferred over other names, and numbered workspaces such as `repo_2` are considered last.
3. A deterministic shallow clone under `~/.cache/symvision/external-repos`.

`SYMVISION_EXTERNAL_REPO_PATHS` is an `os.pathsep`-separated list (`:` on Unix, `;` on Windows). Override the fallback
clone root with `SYMVISION_EXTERNAL_REPO_CACHE`. An existing cache entry must have a matching origin; `symvision` will
report a mismatch instead of overwriting it.

Multiple consecutive pragmas can document multiple consumers for the same definition:

```python
# symvision: config/plugin.toml
# symvision: git@github.com:example/application.git
class ApplicationPlugin:
    ...
```

## Symbols tied to an epic

`--epic-symbol` supports public APIs that are intentionally unused while an active epic is building their consumer:

```console
BD_COMMAND=tools/sase_bead symvision \
  --epic-symbol 'sase-123(create_report)' \
  src/pkg
```

The value has the form `<bead-id>(<symbol-name>)`. The command verifies that the bead exists and is not closed, that
the symbol is a public definition, and that it is still otherwise unused. A closed bead, missing symbol, private
symbol, or already-used symbol makes the exclusion stale and fails the scan.

`symvision` invokes `bd show <bead-id>` by default. Set `BD_COMMAND` to a compatible bead-tracker executable when the
project uses a wrapper or another command. Remove the option once the epic's production consumer lands.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The scan completed without a symbol-visibility violation, or found no Python definitions to check |
| `1` | A visibility rule, pragma, epic-symbol validation, external-repository resolution, or directory check failed |
| `2` | Command-line usage error, such as a missing required argument or an unknown option |

Diagnostics are written to stdout or stderr depending on their category; integrations should use the exit code as the
stable success signal.

## Continuous integration

Run the same command locally and in CI. A small Justfile recipe is enough:

```just
symvision:
    uvx --from symvision symvision src/your_package
```

Pin `symvision` to the version range appropriate for your project when reproducibility is important.

## Development

The repository uses [uv](https://docs.astral.sh/uv/) for environments and dependency installation, and
[just](https://just.systems/) as its task runner. From a clone:

```console
just install
just check
```

`just check` verifies formatting, runs Ruff and strict mypy, dogfoods both `symvision` and
[`toobig`](https://pypi.org/project/toobig/), and executes the pytest suite with a 94% branch-coverage gate. The
package supports Python 3.11 through 3.14 and has no runtime dependencies. Set `SYMVISION_PYTHON` to select the Python
interpreter used by the Justfile, for example `SYMVISION_PYTHON=3.14 just test`.

## Releases

Commits and pull-request titles follow [Conventional Commits](https://www.conventionalcommits.org/). On every push to
`master`, release-please updates or opens a release pull request containing the next version and changelog. Merging
that pull request creates the GitHub release, builds and smoke-tests the wheel in a fresh environment, and publishes
`symvision` to PyPI using trusted publishing (GitHub Actions OIDC), without a long-lived PyPI token.

## License

`symvision` is available under the [MIT License](LICENSE).

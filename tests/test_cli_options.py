"""Focused CLI option and diagnostic tests."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("bad-format", "Invalid --epic-symbol format"),
        ("open(_private)", "symbol '_private' is private"),
        ("missing(orphan)", "bead 'missing' not found"),
        ("closed(orphan)", "bead 'closed' is closed"),
        ("open(absent)", "symbol 'absent' not found"),
    ],
)
def test_epic_symbol_validation_errors(
    entry: str,
    message: str,
    fake_bd: Path,
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/core.py", "def orphan():\n    return 1\n")
    track_repo(repo)

    result = run_symvision(
        repo,
        ["--epic-symbol", entry],
        {"BD_COMMAND": str(fake_bd)},
    )

    assert result.returncode == 1
    assert message in result.stderr


def test_epic_symbol_rejects_already_used_symbol(
    fake_bd: Path,
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/core.py", "def used_symbol():\n    return 1\n")
    write_file(repo, "app.py", "from pkg.core import used_symbol\n")
    track_repo(repo)

    result = run_symvision(
        repo,
        ["--epic-symbol", "open(used_symbol)"],
        {"BD_COMMAND": str(fake_bd)},
    )

    assert result.returncode == 1
    assert "symbol 'used_symbol' is already properly used" in result.stderr


def test_epic_symbol_allows_open_epic(
    fake_bd: Path,
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/core.py", "def future_api():\n    return 1\n")
    track_repo(repo)

    result = run_symvision(
        repo,
        ["--epic-symbol", "open(future_api)"],
        {"BD_COMMAND": str(fake_bd)},
    )

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_exclude_file_can_remove_every_definition(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    core = write_file(repo, "src/pkg/core.py", "def orphan():\n    return 1\n")
    track_repo(repo)

    result = run_symvision(
        repo,
        [
            "--exclude-file",
            str(core),
            "--exclude-file",
            str(repo / "src/pkg/__init__.py"),
        ],
    )

    assert result.returncode == 0
    assert "No Python files found" in result.stderr


def test_exclude_decorator_ignores_decorated_definition(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/core.py",
        "def marker(value):\n    return value\n\n\n@marker\ndef generated():\n    return 1\n",
    )
    write_file(repo, "app.py", "from pkg.core import marker\n")
    track_repo(repo)

    result = run_symvision(repo, ["--exclude-decorator", "marker"])

    assert result.returncode == 0
    assert "All public/private classes/functions are used properly!" in result.stdout


def test_rejects_private_import_from_non_test_file(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/core.py",
        "def public():\n    return _helper()\n\n\ndef _helper():\n    return 1\n",
    )
    write_file(repo, "app.py", "from pkg.core import _helper, public\n")
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "Private functions/classes should not be imported" in result.stderr
    assert "_helper" in result.stderr


def test_rejects_unused_private_symbol(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/core.py",
        "def public():\n    return 1\n\n\ndef _unused():\n    return 2\n",
    )
    write_file(repo, "app.py", "from pkg.core import public\n")
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "Private functions/classes must be used in the file" in result.stderr
    assert "_unused" in result.stderr


def test_entry_point_keeps_public_symbol_alive(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/cli.py", "def launch():\n    return 0\n")
    write_file(repo, "pyproject.toml", '[project.scripts]\npkg = "pkg.cli:launch"\n')
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_pragma_requires_git_repository(
    tmp_path: Path,
    write_file: Callable[[Path, str, str], Path],
    run_symvision: Callable[..., Any],
) -> None:
    repo = tmp_path / "not-a-repo"
    (repo / "src/pkg").mkdir(parents=True)
    write_file(
        repo,
        "src/pkg/core.py",
        "# symvision: config.toml\ndef public():\n    return 1\n",
    )

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "pragmas found but not inside a git repository" in result.stderr

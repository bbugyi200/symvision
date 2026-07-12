"""Local pragma regressions ported from the original bash suite."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


def test_rejects_test_file_pragmas(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/widgets.py",
        "# symvision: tests/test_widgets.py\nclass WidgetFactory:\n    pass\n",
    )
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.widgets import WidgetFactory\n\n\n"
        "def test_widget_factory_usage():\n    WidgetFactory()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "referenced test-support path 'tests/test_widgets.py' is forbidden" in result.stderr
    assert "references from tests or testing utilities are not sufficient" in result.stderr


def test_rejects_testing_dir_pragmas(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/widgets.py",
        "# symvision: src/pkg/testing/helpers.py\nclass WidgetFactory:\n    pass\n",
    )
    write_file(
        repo,
        "src/pkg/testing/helpers.py",
        "from pkg.widgets import WidgetFactory\n\n\n"
        "def make_test_widget():\n    return WidgetFactory()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "referenced test-support path 'src/pkg/testing/helpers.py' is forbidden" in result.stderr
    assert "references from tests or testing utilities are not sufficient" in result.stderr


def test_pragma_not_stale_when_only_test_imports_exist(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/widgets.py",
        "# symvision: docs/reference.toml\nclass WidgetFactory:\n    pass\n",
    )
    write_file(repo, "docs/reference.toml", 'factory = "WidgetFactory"\n')
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.widgets import WidgetFactory\n\n\n"
        "def test_widget_factory():\n    WidgetFactory()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_keeps_non_test_pragmas(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/widgets.py",
        "# symvision: docs/reference.toml\nclass WidgetFactory:\n    pass\n",
    )
    write_file(repo, "docs/reference.toml", 'factory = "WidgetFactory"\n')
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


@pytest.mark.parametrize("extension", ["md", "markdown"])
def test_rejects_markdown_local_pragmas(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
    extension: str,
) -> None:
    repo = make_repo()
    relative_path = f"docs/reference.{extension}"
    write_file(
        repo,
        "src/pkg/widgets.py",
        f"# symvision: {relative_path}\nclass WidgetFactory:\n    pass\n",
    )
    write_file(repo, relative_path, "WidgetFactory is referenced from documentation.\n")
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert f"referenced markdown path '{relative_path}' is forbidden" in result.stderr
    assert "markdown docs are not valid symvision consumers" in result.stderr

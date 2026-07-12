"""Usage-analysis regressions ported from the original bash suite."""

from collections.abc import Callable
from pathlib import Path
from typing import Any


def test_module_alias_usage_from_tracked_tests(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/records.py", "class NotificationStoreRecord:\n    pass\n")
    write_file(
        repo,
        "tests/test_records.py",
        "from pkg import records as facade\n\n\ndef test_record_usage():\n"
        "    facade.NotificationStoreRecord()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "Unused public functions/classes" in result.stdout
    assert "NotificationStoreRecord" in result.stdout


def test_from_import_alias_usage_from_tracked_tests(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/widgets.py", "class WidgetFactory:\n    pass\n")
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.widgets import WidgetFactory as Factory\n\n\n"
        "def test_widget_factory_usage():\n    Factory()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "Unused public functions/classes" in result.stdout
    assert "WidgetFactory" in result.stdout


def test_module_alias_usage_from_non_test_file(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/records.py", "class NotificationStoreRecord:\n    pass\n")
    write_file(
        repo,
        "app.py",
        "from pkg import records as facade\n\n\ndef use_record():\n"
        "    return facade.NotificationStoreRecord()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "All public/private classes/functions are used properly!" in result.stdout


def test_allows_private_imports_from_tracked_tests(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/widgets.py",
        'def build_widget():\n    return _helper()\n\n\ndef _helper():\n    return "widget"\n',
    )
    write_file(
        repo,
        "app.py",
        "from pkg.widgets import build_widget\n\n\ndef main():\n    return build_widget()\n",
    )
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.widgets import _helper, build_widget\n\n\n"
        "def test_private_helper_usage():\n    assert _helper() == build_widget()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "All public/private classes/functions are used properly!" in result.stdout


def test_fails_when_public_symbol_only_used_in_tests(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/widgets.py", 'def build_widget():\n    return "widget"\n')
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.widgets import build_widget\n\n\n"
        'def test_build_widget():\n    assert build_widget() == "widget"\n',
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "Unused public functions/classes" in result.stdout
    assert "build_widget" in result.stdout


def test_ignores_public_symbols_defined_under_testing_dir(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/testing/helpers.py", "class WidgetTestHelper:\n    pass\n")
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.testing.helpers import WidgetTestHelper\n\n\n"
        "def test_widget_test_helper():\n    assert WidgetTestHelper()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_ignores_testing_dir_usage_for_public_symbols(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/widgets.py", 'def build_widget():\n    return "widget"\n')
    write_file(
        repo,
        "src/pkg/testing/helpers.py",
        "from pkg.widgets import build_widget\n\n\n"
        "def make_test_widget():\n    return build_widget()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "Unused public functions/classes" in result.stdout
    assert "build_widget" in result.stdout


def test_allows_private_imports_from_testing_dir(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/widgets.py",
        'def build_widget():\n    return _helper()\n\n\ndef _helper():\n    return "widget"\n',
    )
    write_file(
        repo,
        "app.py",
        "from pkg.widgets import build_widget\n\n\ndef main():\n    return build_widget()\n",
    )
    write_file(
        repo,
        "src/pkg/testing/helpers.py",
        "from pkg.widgets import _helper\n\n\ndef make_test_widget():\n    return _helper()\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "All public/private classes/functions are used properly!" in result.stdout


def test_passes_when_symbol_used_in_tests_and_non_tests(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(repo, "src/pkg/widgets.py", 'def build_widget():\n    return "widget"\n')
    write_file(
        repo,
        "app.py",
        "from pkg.widgets import build_widget\n\n\ndef main():\n    return build_widget()\n",
    )
    write_file(
        repo,
        "tests/test_widgets.py",
        "from pkg.widgets import build_widget\n\n\n"
        'def test_build_widget():\n    assert build_widget() == "widget"\n',
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "All public/private classes/functions are used properly!" in result.stdout


def test_unused_public_class_dependency_still_fails(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    write_file(
        repo,
        "src/pkg/items.py",
        "from dataclasses import dataclass\n\n\n@dataclass\nclass StaleRecord:\n"
        "    name: str\n\n\n@dataclass\nclass UnusedWrapper:\n    record: StaleRecord\n",
    )
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert "StaleRecord" in result.stdout
    assert "UnusedWrapper" in result.stdout

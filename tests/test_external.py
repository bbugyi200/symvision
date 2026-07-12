"""External-repository regressions ported from the original bash suite."""

from collections.abc import Callable
from pathlib import Path
from typing import Any


def _make_external(
    make_repo: Callable[..., Path], name: str, remote_url: str, parent: Path | None = None
) -> Path:
    return make_repo(name, parent=parent, origin=remote_url, external=True)


def _write_external_pragma(
    write_file: Callable[[Path, str, str], Path], repo: Path, remote_url: str
) -> None:
    write_file(
        repo,
        "src/pkg/widgets.py",
        f"# symvision: {remote_url}\nclass WidgetFactory:\n    pass\n",
    )


def test_uri_pragma_passes_when_external_repo_imports_symbol(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-consumer.git"
    repo = make_repo()
    external_repo = _make_external(make_repo, "consumer-repo", remote_url)
    _write_external_pragma(write_file, repo, remote_url)
    write_file(
        external_repo,
        "consumer/widgets.py",
        "from pkg.widgets import WidgetFactory\n\n\ndef build_widget():\n"
        "    return WidgetFactory()\n",
    )
    track_repo(repo)
    track_repo(external_repo)

    result = run_symvision(repo, env={"SYMVISION_EXTERNAL_REPO_PATHS": str(external_repo)})

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_uri_pragma_prefers_canonical_sibling_checkout(
    tmp_path: Path,
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-canonical-consumer.git"
    repo = make_repo("producer", parent=tmp_path)
    stale_repo = _make_external(make_repo, "symvision-canonical-consumer_10", remote_url, tmp_path)
    canonical_repo = _make_external(make_repo, "symvision-canonical-consumer", remote_url, tmp_path)
    _write_external_pragma(write_file, repo, remote_url)
    write_file(stale_repo, "consumer/widgets.py", 'def build_widget():\n    return "widget"\n')
    write_file(
        canonical_repo,
        "consumer/widgets.py",
        "from pkg.widgets import WidgetFactory\n\n\ndef build_widget():\n"
        "    return WidgetFactory()\n",
    )
    for path in (repo, stale_repo, canonical_repo):
        track_repo(path)

    result = run_symvision(repo)

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_uri_pragma_checks_later_matching_checkout(
    tmp_path: Path,
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-later-consumer.git"
    repo = make_repo("producer", parent=tmp_path)
    stale_repo = _make_external(make_repo, "stale", remote_url)
    canonical_repo = _make_external(make_repo, "symvision-later-consumer", remote_url, tmp_path)
    _write_external_pragma(write_file, repo, remote_url)
    write_file(stale_repo, "consumer/widgets.py", 'def build_widget():\n    return "widget"\n')
    write_file(
        canonical_repo,
        "consumer/widgets.py",
        "from pkg.widgets import WidgetFactory\n\n\ndef build_widget():\n"
        "    return WidgetFactory()\n",
    )
    for path in (repo, stale_repo, canonical_repo):
        track_repo(path)

    result = run_symvision(repo, env={"SYMVISION_EXTERNAL_REPO_PATHS": str(stale_repo)})

    assert result.returncode == 0
    assert "No public functions or classes found!" in result.stderr


def test_uri_pragma_fails_when_external_repo_lacks_symbol(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-empty-consumer.git"
    repo = make_repo()
    external_repo = _make_external(make_repo, "empty-consumer", remote_url)
    _write_external_pragma(write_file, repo, remote_url)
    write_file(external_repo, "consumer/widgets.py", 'def build_widget():\n    return "widget"\n')
    track_repo(repo)
    track_repo(external_repo)

    result = run_symvision(repo, env={"SYMVISION_EXTERNAL_REPO_PATHS": str(external_repo)})

    assert result.returncode == 1
    assert (
        f"external repository '{remote_url}' does not reference symbol 'WidgetFactory'"
        in result.stderr
    )


def test_uri_pragma_fails_when_external_repo_cannot_resolve(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    repo = make_repo()
    remote_url = f"file://{repo / 'missing-consumer'}"
    _write_external_pragma(write_file, repo, remote_url)
    track_repo(repo)

    result = run_symvision(repo)

    assert result.returncode == 1
    assert f"could not resolve external repository '{remote_url}'" in result.stderr


def test_uri_pragma_ignores_external_test_only_usage(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-test-only-consumer.git"
    repo = make_repo()
    external_repo = _make_external(make_repo, "test-consumer", remote_url)
    _write_external_pragma(write_file, repo, remote_url)
    write_file(
        external_repo,
        "tests/test_widgets.py",
        "from pkg.widgets import WidgetFactory\n\n\n"
        "def test_widget_factory():\n    assert WidgetFactory()\n",
    )
    track_repo(repo)
    track_repo(external_repo)

    result = run_symvision(repo, env={"SYMVISION_EXTERNAL_REPO_PATHS": str(external_repo)})

    assert result.returncode == 1
    assert "does not reference symbol 'WidgetFactory'" in result.stderr


def test_uri_pragma_ignores_external_testing_dir_usage(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-testing-only-consumer.git"
    repo = make_repo()
    external_repo = _make_external(make_repo, "testing-consumer", remote_url)
    _write_external_pragma(write_file, repo, remote_url)
    write_file(
        external_repo,
        "consumer/testing/helpers.py",
        "from pkg.widgets import WidgetFactory\n\n\ndef make_widget():\n"
        "    return WidgetFactory()\n",
    )
    track_repo(repo)
    track_repo(external_repo)

    result = run_symvision(repo, env={"SYMVISION_EXTERNAL_REPO_PATHS": str(external_repo)})

    assert result.returncode == 1
    assert "does not reference symbol 'WidgetFactory'" in result.stderr


def test_external_api_root_proves_return_record_surface(
    make_repo: Callable[..., Path],
    write_file: Callable[[Path, str, str], Path],
    track_repo: Callable[[Path], None],
    run_symvision: Callable[..., Any],
) -> None:
    remote_url = "https://github.com/example/symvision-api-surface-consumer.git"
    repo = make_repo()
    external_repo = _make_external(make_repo, "api-consumer", remote_url)
    write_file(
        repo,
        "src/pkg/items.py",
        "from dataclasses import dataclass\n\n\n@dataclass\nclass ItemEntry:\n"
        "    name: str\n\n\n@dataclass\nclass ItemListing:\n"
        "    entries: list[ItemEntry]\n\n\n"
        f"# symvision: {remote_url}\ndef list_items() -> ItemListing:\n"
        '    return ItemListing([ItemEntry("one")])\n',
    )
    write_file(
        external_repo,
        "consumer/items.py",
        "from pkg.items import list_items\n\n\ndef render_items():\n"
        "    return [entry.name for entry in list_items().entries]\n",
    )
    track_repo(repo)
    track_repo(external_repo)

    result = run_symvision(repo, env={"SYMVISION_EXTERNAL_REPO_PATHS": str(external_repo)})

    assert result.returncode == 0
    assert "All public/private classes/functions are used properly!" in result.stdout

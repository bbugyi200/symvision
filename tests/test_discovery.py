"""Focused tests for file and project metadata discovery."""

import subprocess
from pathlib import Path

from symvision.discovery import (
    build_tracked_module_names,
    extract_entrypoint_symbols,
    find_pyproject_toml,
    find_python_files,
    find_usage_only_python_files,
)


def test_extracts_every_supported_entry_point_section(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\nname = 'example'\n"
        "[project.scripts]\ncli = 'pkg.cli:main'\nignored = 'no-colon'\n"
        "[project.gui-scripts]\ngui = 'pkg.gui:launch'\n"
        "[project.entry-points.'example.plugins']\nplugin = 'pkg.plugin:register'\n",
        encoding="utf-8",
    )

    assert extract_entrypoint_symbols(pyproject) == {"main", "launch", "register"}


def test_python_discovery_and_usage_only_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "src/pkg/testing").mkdir(parents=True)
    (repo / "src/pkg/core.py").write_text("", encoding="utf-8")
    (repo / "src/pkg/test_core.py").write_text("", encoding="utf-8")
    (repo / "src/pkg/testing/helper.py").write_text("", encoding="utf-8")
    (repo / "src/pkg/.venv").mkdir()
    (repo / "src/pkg/.venv/hidden.py").write_text("", encoding="utf-8")
    (repo / "app.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    definitions = find_python_files(repo / "src/pkg")
    all_python = find_python_files(repo / "src/pkg", exclude_test_dirs=False)
    usage = find_usage_only_python_files(repo / "src/pkg", repo, {repo / "ignored.py"})

    assert definitions == [repo / "src/pkg/core.py"]
    assert set(all_python) == {
        repo / "src/pkg/core.py",
        repo / "src/pkg/test_core.py",
        repo / "src/pkg/testing/helper.py",
    }
    assert usage == [repo / "app.py"]
    assert find_usage_only_python_files(repo / "src/pkg", None, set()) == []


def test_module_names_and_pyproject_walk(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    package = repo / "src/pkg"
    package.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='pkg'\n", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "feature.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    names = build_tracked_module_names(repo)

    assert {"pkg", "pkg.feature", "src.pkg", "src.pkg.feature"} <= names
    assert find_pyproject_toml(package) == repo / "pyproject.toml"
    assert find_pyproject_toml(tmp_path / "missing") is None
    assert build_tracked_module_names(None) == set()

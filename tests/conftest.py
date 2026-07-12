"""Shared fixtures for symvision regression tests."""

import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class CliResult:
    """Captured result from one in-process CLI invocation."""

    returncode: int
    stdout: str
    stderr: str


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., Path]:
    """Create git repositories with the standard regression-test layout."""

    def factory(
        name: str = "producer",
        *,
        parent: Path | None = None,
        origin: str | None = None,
        external: bool = False,
    ) -> Path:
        repo = (parent or tmp_path) / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        if origin is not None:
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
        if external:
            (repo / "consumer").mkdir()
            (repo / "consumer" / "__init__.py").write_text("", encoding="utf-8")
            (repo / "tests").mkdir()
        else:
            (repo / "src" / "pkg").mkdir(parents=True)
            (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (repo / "tests").mkdir()
            (repo / "docs").mkdir()
        return repo

    return factory


@pytest.fixture
def track_repo() -> Callable[[Path], None]:
    """Return a helper that adds every current repository file to git's index."""

    def track(repo: Path) -> None:
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

    return track


@pytest.fixture
def write_file() -> Callable[[Path, str], Path]:
    """Return a helper for writing a repository-relative text file."""

    def write(repo: Path, relative_path: str, content: str) -> Path:
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    return write


@pytest.fixture
def run_symvision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Callable[..., CliResult]:
    """Run the CLI in-process so pytest-cov observes the implementation."""

    def run(
        repo: Path,
        args: Sequence[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> CliResult:
        from symvision.cli import main

        monkeypatch.chdir(repo)
        monkeypatch.setattr(sys, "argv", ["symvision", "src/pkg", *args])
        for name, value in (env or {}).items():
            monkeypatch.setenv(name, value)
        returncode = main()
        captured = capsys.readouterr()
        return CliResult(returncode, captured.out, captured.err)

    return run


@pytest.fixture
def fake_bd(tmp_path: Path) -> Path:
    """Create a deterministic stand-in for the bead tracker CLI."""

    executable = tmp_path / "fake-bd"
    executable.write_text(
        "#!/bin/sh\n"
        'case "$2" in\n'
        "  missing) exit 1 ;;\n"
        '  closed) echo "CLOSED" ;;\n'
        '  *) echo "OPEN" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


@pytest.fixture(autouse=True)
def isolate_external_repo_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep resolver fallback state and ambient checkout paths out of tests."""

    monkeypatch.setenv("SYMVISION_EXTERNAL_REPO_CACHE", str(tmp_path / "external-cache"))
    monkeypatch.delenv("SYMVISION_EXTERNAL_REPO_PATHS", raising=False)
    monkeypatch.delenv("BD_COMMAND", raising=False)
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)
    monkeypatch.delenv("COVERAGE_PROCESS_START", raising=False)

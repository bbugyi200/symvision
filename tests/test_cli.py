"""CLI smoke tests."""

import subprocess
import sys
from pathlib import Path


def _run_symvision(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "symvision", str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "symvision", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Find unused public Python function" in result.stdout


def test_happy_path(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "core.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    (package / "consumer.py").write_text(
        "from package.core import Widget\n\nVALUE = Widget()\n", encoding="utf-8"
    )

    result = _run_symvision(package)

    assert result.returncode == 0
    assert "used properly" in result.stdout


def test_unused_public_symbol_is_a_violation(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "core.py").write_text("def orphan():\n    return 1\n", encoding="utf-8")

    result = _run_symvision(package)

    assert result.returncode == 1
    assert "Unused public functions/classes" in result.stdout
    assert "orphan" in result.stdout


def test_missing_directory_is_a_violation(tmp_path: Path) -> None:
    result = _run_symvision(tmp_path / "missing")

    assert result.returncode == 1
    assert "is not a directory" in result.stderr

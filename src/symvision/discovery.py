"""Filesystem discovery and project metadata helpers."""

import subprocess
import tomllib
from pathlib import Path


def find_git_tracked_files(git_root: Path) -> list[Path]:
    """Return all tracked files from a git repository."""
    result = subprocess.run(
        ["git", "-C", str(git_root), "ls-files", "-z"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [git_root / rel_path for rel_path in result.stdout.split("\0") if rel_path]


def is_markdown_reference_path(ref_path: str) -> bool:
    """Return whether a local symvision pragma points at a markdown file."""
    return Path(ref_path).suffix.lower() in {".md", ".markdown"}


def is_test_reference_path(ref_path: str) -> bool:
    """Return whether a symvision pragma points at a test-support reference."""
    path = Path(ref_path)
    return is_test_support_file_path(path)


def is_test_support_file_path(path: Path) -> bool:
    """Return whether a Python path is test or test-support code."""
    if any(part in {"test", "tests", "testing"} for part in path.parts):
        return True
    return path.suffix == ".py" and path.name.startswith("test_")


def find_python_files(directory: Path, exclude_test_dirs: bool = True) -> list[Path]:
    """Find all .py files in directory, optionally excluding test-support paths."""
    exclude_dirs = {".venv", "venv"}

    python_files = []
    for py_file in directory.rglob("*.py"):
        relative_path = py_file.relative_to(directory)
        if any(part in exclude_dirs for part in relative_path.parts):
            continue
        if exclude_test_dirs and is_test_support_file_path(relative_path):
            continue
        python_files.append(py_file)

    return python_files


def _find_git_tracked_python_files(git_root: Path) -> list[Path]:
    """Return tracked Python files from a git repo."""
    result = subprocess.run(
        ["git", "-C", str(git_root), "ls-files", "-z", "--", "*.py"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    return [git_root / rel_path for rel_path in result.stdout.split("\0") if rel_path]


def _is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether path is under parent, resolving both first."""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def find_usage_only_python_files(
    target_directory: Path, git_root: Path | None, excluded: set[Path]
) -> list[Path]:
    """Find tracked Python files outside the analyzed definition tree."""
    if git_root is None:
        return []

    usage_files = []
    for py_file in _find_git_tracked_python_files(git_root):
        resolved = py_file.resolve()
        if resolved in excluded:
            continue
        if _is_relative_to(resolved, target_directory):
            continue
        usage_files.append(py_file)
    return usage_files


def _module_name_from_parts(parts: tuple[str, ...]) -> str | None:
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def _python_module_names(py_file: Path, git_root: Path) -> set[str]:
    """Return plausible import module names for a tracked Python file."""
    try:
        rel_parts = py_file.resolve().relative_to(git_root.resolve()).with_suffix("").parts
    except ValueError:
        return set()

    module_names: set[str] = set()
    for index in range(len(rel_parts)):
        module_name = _module_name_from_parts(tuple(rel_parts[index:]))
        if module_name:
            module_names.add(module_name)
    return module_names


def build_tracked_module_names(git_root: Path | None) -> set[str]:
    """Build a broad set of module names resolvable from tracked Python files."""
    if git_root is None:
        return set()

    module_names: set[str] = set()
    for py_file in _find_git_tracked_python_files(git_root):
        module_names.update(_python_module_names(py_file, git_root))
    return module_names


def find_pyproject_toml(directory: Path) -> Path | None:
    """Walk up from directory to find the nearest pyproject.toml."""
    current = directory.resolve()
    while True:
        candidate = current / "pyproject.toml"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def extract_entrypoint_symbols(pyproject_path: Path) -> set[str]:
    """Extract function names from pyproject.toml entry points.

    Parses [project.scripts], [project.gui-scripts], and [project.entry-points.*]
    sections, extracting the function name from each "module.path:function_name" value.
    """
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    symbols: set[str] = set()
    project = data.get("project", {})

    for section_key in ("scripts", "gui-scripts"):
        section = project.get(section_key, {})
        for value in section.values():
            if ":" in value:
                func_name = value.rsplit(":", 1)[1]
                symbols.add(func_name)

    for group in project.get("entry-points", {}).values():
        for value in group.values():
            if ":" in value:
                func_name = value.rsplit(":", 1)[1]
                symbols.add(func_name)

    return symbols

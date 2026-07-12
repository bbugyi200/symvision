"""Command-line orchestration for symvision analysis."""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from symvision.api import build_public_api_dependency_graph, reachable_api_dependencies
from symvision.discovery import (
    build_tracked_module_names,
    extract_entrypoint_symbols,
    find_pyproject_toml,
    find_python_files,
    find_usage_only_python_files,
    is_test_support_file_path,
)
from symvision.git import get_git_root
from symvision.models import FileInfo, PragmaInfo
from symvision.pragmas import validate_pragmas
from symvision.scanner import batch_check_private_in_file, batch_search_usage, extract_file_info


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find unused public Python function and class definitions"
    )
    parser.add_argument("directory", type=Path, help="Directory to search for Python files")
    parser.add_argument(
        "--exclude-file",
        action="append",
        default=[],
        help="Exclude a file from analysis (can be repeated)",
    )
    parser.add_argument(
        "--epic-symbol",
        action="append",
        default=[],
        help=(
            "Exclude a symbol tied to an open epic bead from unused-symbol analysis."
            " Format: <bead_id>(<symbol_name>). Can be repeated."
        ),
    )
    parser.add_argument(
        "--exclude-decorator",
        action="append",
        default=[],
        help=(
            "Exclude any function/class decorated with this decorator name"
            " from unused-symbol analysis. Can be repeated."
        ),
    )
    parser.add_argument(
        "-E",
        "--external-repo-path",
        action="append",
        default=[],
        type=Path,
        help=(
            "Local external repository checkout to use for URI pragmas. Can be repeated."
            " SYMVISION_EXTERNAL_REPO_PATHS also accepts os.pathsep-separated paths."
        ),
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: {args.directory} is not a directory", file=sys.stderr)
        return 1

    git_root = get_git_root(args.directory)

    # Find all definition Python files excluding test directories
    python_files = find_python_files(args.directory)

    # Apply --exclude-file filters
    excluded: set[Path] = set()
    if args.exclude_file:
        excluded = {Path(p).resolve() for p in args.exclude_file}
        python_files = [f for f in python_files if f.resolve() not in excluded]

    if not python_files:
        print("No Python files found", file=sys.stderr)
        return 0

    usage_only_python_files = find_usage_only_python_files(args.directory, git_root, excluded)

    # Build the set of excluded decorator names
    exclude_decorators = set(args.exclude_decorator) if args.exclude_decorator else None

    # === SINGLE PASS: Read each file once and extract everything ===
    file_infos: list[FileInfo] = []
    for py_file in python_files:
        info = extract_file_info(py_file, exclude_decorators)
        if info is not None:
            file_infos.append(info)

    usage_only_file_infos: list[FileInfo] = []
    for py_file in usage_only_python_files:
        info = extract_file_info(py_file, exclude_decorators)
        if info is not None:
            usage_only_file_infos.append(info)

    non_test_usage_file_infos = file_infos + [
        info
        for info in usage_only_file_infos
        if not is_test_support_file_path(
            info.path.relative_to(git_root) if git_root is not None else info.path
        )
    ]

    # Collect all public symbols: {symbol_name: [file_path, ...]}
    all_symbols: dict[str, list[Path]] = {}
    for info in file_infos:
        for symbol in info.public_symbols:
            if symbol not in all_symbols:
                all_symbols[symbol] = []
            all_symbols[symbol].append(info.path)
    public_api_dependency_graph = build_public_api_dependency_graph(file_infos, set(all_symbols))

    # Exclude symbols referenced as entry points in pyproject.toml
    pyproject_path = find_pyproject_toml(args.directory)
    if pyproject_path:
        entrypoint_symbols = extract_entrypoint_symbols(pyproject_path)
        for sym in entrypoint_symbols:
            all_symbols.pop(sym, None)

    # Collect all private symbols: {symbol_name: [file_path, ...]}
    all_private_symbols: dict[str, list[Path]] = {}
    for info in file_infos:
        for symbol in info.private_symbols:
            if symbol not in all_private_symbols:
                all_private_symbols[symbol] = []
            all_private_symbols[symbol].append(info.path)

    # Collect all pragmas
    all_pragmas: dict[str, list[PragmaInfo]] = {}
    for info in file_infos:
        all_pragmas.update(info.pragmas)

    # === SINGLE BATCH: Find all imported symbols at once ===
    # We need to check usage for: all public symbols + all private symbols + pragma symbols
    all_symbols_to_check = (
        set(all_symbols.keys()) | set(all_private_symbols.keys()) | set(all_pragmas.keys())
    )
    tracked_modules = build_tracked_module_names(git_root)
    imported_symbols = batch_search_usage(
        all_symbols_to_check, non_test_usage_file_infos, tracked_modules
    )
    env_external_repo_paths = [
        Path(path)
        for path in os.environ.get("SYMVISION_EXTERNAL_REPO_PATHS", "").split(os.pathsep)
        if path
    ]
    external_repo_paths = list(args.external_repo_path) + env_external_repo_paths

    # Apply --epic-symbol filters
    epic_errors = []
    validated_epic_symbols = []
    for entry in args.epic_symbol:
        # 1. Parse format: <bead_id>(<symbol_name>)
        m = re.match(r"^(.+)\(([^)]+)\)$", entry)
        if not m:
            epic_errors.append(
                f"Error: Invalid --epic-symbol format '{entry}'."
                " Expected format: <bead_id>(<symbol_name>)"
            )
            continue
        bead_id, symbol_name = m.group(1), m.group(2)

        # 2. Reject private symbols
        if symbol_name.startswith("_"):
            epic_errors.append(
                f"Error: --epic-symbol '{entry}': symbol '{symbol_name}' is private."
                " Only public symbols can be excluded."
            )
            continue

        # 3. Check bead is open
        bd_cmd = os.environ.get("BD_COMMAND", "bd")
        result = subprocess.run(
            [bd_cmd, "show", bead_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            epic_errors.append(
                f"Error: --epic-symbol '{entry}': bead '{bead_id}' not found."
                " Remove this --epic-symbol entry."
            )
            continue
        if "CLOSED" in result.stdout:
            epic_errors.append(
                f"Error: --epic-symbol '{entry}': bead '{bead_id}' is closed."
                " Remove this stale --epic-symbol entry and clean up the symbol."
            )
            continue

        # 4. Check symbol exists
        if symbol_name not in all_symbols:
            epic_errors.append(
                f"Error: --epic-symbol '{entry}': symbol '{symbol_name}' not found"
                " as a public definition. Remove this --epic-symbol entry."
            )
            continue

        # 5. Check symbol actually needs ignoring (not already used)
        if symbol_name in imported_symbols:
            epic_errors.append(
                f"Error: --epic-symbol '{entry}': symbol '{symbol_name}' is already"
                " properly used. Remove this unnecessary --epic-symbol entry."
            )
            continue

        validated_epic_symbols.append(symbol_name)

    if epic_errors:
        for err in epic_errors:
            print(err, file=sys.stderr)
        return 1

    for symbol in validated_epic_symbols:
        all_symbols.pop(symbol, None)

    # Validate pragmas (uses pre-computed imported_symbols instead of re-scanning)
    externally_used_symbols: set[str] = set()
    if all_pragmas:
        if git_root is None:
            print(
                "Error: symvision pragmas found but not inside a git repository",
                file=sys.stderr,
            )
            return 1

        pragma_errors = validate_pragmas(
            all_pragmas,
            git_root,
            imported_symbols,
            tracked_modules,
            external_repo_paths,
            externally_used_symbols,
        )
        if pragma_errors:
            for err in pragma_errors:
                print(err, file=sys.stderr)
            return 1

        imported_symbols.update(
            reachable_api_dependencies(externally_used_symbols, public_api_dependency_graph)
        )

        # Remove pragma-covered symbols from the unused check
        for symbol_name in all_pragmas:
            all_symbols.pop(symbol_name, None)

    if not all_symbols:
        print("No public functions or classes found!", file=sys.stderr)
        return 0

    # Check that private symbols do NOT match import patterns
    imported_private_symbols = []
    imported_private_symbol_names = batch_search_usage(
        set(all_private_symbols.keys()), non_test_usage_file_infos, tracked_modules
    )
    for symbol_name, def_files in all_private_symbols.items():
        if symbol_name in imported_private_symbol_names:
            imported_private_symbols.append((symbol_name, def_files))

    if imported_private_symbols:
        print(
            "Error: Private functions/classes should not be imported. Make these public if they"
            " need to be imported by non-test files!:",
            file=sys.stderr,
        )
        for symbol_name, def_files in sorted(imported_private_symbols):
            for file_path in def_files:
                print(f"  {symbol_name} in {file_path}", file=sys.stderr)
        return 1

    # Check that private symbols ARE used in their own file (using cached content)
    unused_private_symbols = []
    for info in file_infos:
        if info.private_symbols:
            _, unused = batch_check_private_in_file(info)
            for name in unused:
                unused_private_symbols.append((name, info.path))

    if unused_private_symbols:
        print(
            "Error: Private functions/classes must be used in the file where they are defined:",
            file=sys.stderr,
        )
        for symbol_name, file_path in sorted(unused_private_symbols):
            print(f"  {symbol_name} in {file_path}", file=sys.stderr)
        return 1

    # Determine unused public symbols (using pre-computed imported_symbols)
    unused_symbols = []
    for symbol_name, def_files in all_symbols.items():
        if symbol_name not in imported_symbols:
            unused_symbols.append((symbol_name, def_files))

    # Report results
    if unused_symbols:
        print(
            "Unused public functions/classes. Make these private if they are used only within the"
            " file they are defined. If the functions/classes are completely unused, you should"
            " delete them:"
        )
        for symbol_name, def_files in sorted(unused_symbols):
            for file_path in def_files:
                print(f"  {symbol_name} in {file_path}")
        return 1

    print("All public/private classes/functions are used properly!")
    return 0

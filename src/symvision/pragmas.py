"""Pragma validation for local and external references."""

import re
from pathlib import Path

from symvision.discovery import is_markdown_reference_path, is_test_reference_path
from symvision.external import (
    external_repo_references_symbol,
    is_external_repo_target,
    resolve_external_repo_roots,
)
from symvision.models import PragmaInfo


def validate_pragmas(
    all_pragmas: dict[str, list[PragmaInfo]],
    git_root: Path,
    imported_symbols: set[str],
    tracked_modules: set[str],
    external_repo_paths: list[Path],
    externally_used_symbols: set[str],
) -> list[str]:
    """Validate all collected pragmas and return a list of error strings."""
    errors: list[str] = []

    for name, pragma_list in all_pragmas.items():
        # Use first pragma for symbol-level error prefix
        first = pragma_list[0]

        # Symbol-level check: pragma on private symbol
        if name.startswith("_"):
            prefix = f"Error: symvision pragma in {first.source_file}:{first.pragma_line}:"
            errors.append(f"{prefix} pragma cannot be applied to private symbol '{name}'")
            continue

        test_pragma_errors = []
        for pragma in pragma_list:
            if not is_external_repo_target(pragma.ref_path) and is_test_reference_path(
                pragma.ref_path
            ):
                prefix = f"Error: symvision pragma in {pragma.source_file}:{pragma.pragma_line}:"
                test_pragma_errors.append(
                    f"{prefix} referenced test-support path '{pragma.ref_path}' is forbidden"
                    " because references from tests or testing utilities are not sufficient to"
                    " keep a public symbol used; delete the symbol, make it private and call it"
                    " from a non-test path, or use a non-test pragma target"
                )
        if test_pragma_errors:
            errors.extend(test_pragma_errors)
            continue

        # Symbol-level check: stale pragma (symbol already imported by Python files)
        if name in imported_symbols:
            prefix = f"Error: symvision pragma in {first.source_file}:{first.pragma_line}:"
            errors.append(
                f"{prefix} symbol '{name}' is already imported by other Python files."
                " Remove this unnecessary pragma"
            )
            continue

        # Per-pragma checks
        for pragma in pragma_list:
            prefix = f"Error: symvision pragma in {pragma.source_file}:{pragma.pragma_line}:"
            if is_external_repo_target(pragma.ref_path):
                external_repo_roots, resolve_error = resolve_external_repo_roots(
                    pragma.ref_path, git_root, external_repo_paths
                )
                if not external_repo_roots:
                    errors.append(f"{prefix} {resolve_error}")
                    continue

                if any(
                    external_repo_references_symbol(name, external_repo_root, tracked_modules)
                    for external_repo_root in external_repo_roots
                ):
                    externally_used_symbols.add(name)
                else:
                    errors.append(
                        f"{prefix} external repository '{pragma.ref_path}'"
                        f" does not reference symbol '{name}'"
                    )
                continue

            if is_markdown_reference_path(pragma.ref_path):
                errors.append(
                    f"{prefix} referenced markdown path '{pragma.ref_path}' is forbidden"
                    " because markdown docs are not valid symvision consumers; use a"
                    " code or configuration reference instead"
                )
                continue

            ref_file = git_root / pragma.ref_path

            # Referenced file doesn't exist
            if not ref_file.is_file():
                errors.append(f"{prefix} referenced file '{pragma.ref_path}' does not exist")
                continue

            # Referenced file inside src/
            try:
                ref_file.resolve().relative_to((git_root / "src").resolve())
                errors.append(f"{prefix} referenced file '{pragma.ref_path}' is inside src/")
                continue
            except ValueError:
                pass  # Not inside src/ — good

            # Check that referenced file actually contains the symbol name
            try:
                ref_content = ref_file.read_text(encoding="utf-8")
                if not re.search(rf"\b{re.escape(name)}\b", ref_content):
                    errors.append(
                        f"{prefix} referenced file '{pragma.ref_path}'"
                        f" does not contain a reference to symbol '{name}'"
                    )
            except OSError as e:
                errors.append(f"{prefix} could not read referenced file '{pragma.ref_path}': {e}")

    return errors

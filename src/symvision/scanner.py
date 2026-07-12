"""Single-pass Python AST scanning and symbol usage analysis."""

import ast
import re
import sys
from pathlib import Path

from symvision.models import FileInfo, PragmaInfo


def _get_decorator_names(node: ast.AST) -> set[str]:
    """Extract the simple names of all decorators on a function/class node.

    For a plain ``@foo`` decorator the name is ``"foo"``.
    For a dotted ``@foo.bar`` or call ``@foo(...)`` the outermost name is used.
    """
    names: set[str] = set()
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name):
            names.add(dec.id)
        elif isinstance(dec, ast.Attribute):
            # Walk to the root Name of a dotted expression like foo.bar.baz
            inner: ast.expr = dec
            while isinstance(inner, ast.Attribute):
                inner = inner.value
            if isinstance(inner, ast.Name):
                names.add(inner.id)
        elif isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                inner = func
                while isinstance(inner, ast.Attribute):
                    inner = inner.value
                if isinstance(inner, ast.Name):
                    names.add(inner.id)
    return names


def _add_module_alias(info: FileInfo, alias_name: str, module_name: str) -> None:
    """Record an alias that may later qualify attribute usage."""
    if not alias_name or not module_name:
        return
    info.module_aliases.setdefault(alias_name, set()).add(module_name)


def _attribute_chain(node: ast.AST) -> tuple[str, ...] | None:
    """Return dotted attribute components for an expression, if simple enough."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if not isinstance(current, ast.Name):
        return None

    parts.append(current.id)
    parts.reverse()
    return tuple(parts)


def _referenced_names(node: ast.AST | None) -> set[str]:
    """Collect simple public-looking names referenced by an expression."""
    if node is None:
        return set()

    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return {name for name in names if not name.startswith("_")}


def _call_name(node: ast.AST) -> str | None:
    """Return the simple function/class name for a call expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_dataclass_definition(node: ast.ClassDef) -> bool:
    """Return whether a class definition is decorated as a dataclass."""
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute):
            chain = _attribute_chain(target)
            if chain and chain[-1] == "dataclass":
                return True
    return False


def _function_api_dependency_candidates(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    """Collect explicit public API dependencies from a public function."""
    candidates = _referenced_names(node.returns)
    args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
    if node.args.vararg is not None:
        args.append(node.args.vararg)
    if node.args.kwarg is not None:
        args.append(node.args.kwarg)
    for arg in args:
        candidates.update(_referenced_names(arg.annotation))

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _call_name(child.func)
            if name and not name.startswith("_"):
                candidates.add(name)
    return candidates


def _class_api_dependency_candidates(node: ast.ClassDef) -> set[str]:
    """Collect explicit public API dependencies from a public class."""
    candidates: set[str] = set()
    for base in node.bases:
        candidates.update(_referenced_names(base))

    if _is_dataclass_definition(node):
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign):
                candidates.update(_referenced_names(stmt.annotation))

    return candidates


def _collect_usage_info(tree: ast.AST, info: FileInfo) -> None:
    """Collect import and alias-qualified attribute usage using the AST."""

    class Visitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
            for alias in node.names:
                if alias.asname:
                    _add_module_alias(info, alias.asname, alias.name)
                else:
                    root_name = alias.name.split(".", 1)[0]
                    _add_module_alias(info, root_name, root_name)
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
            if node.module is None:
                self.generic_visit(node)
                return

            for alias in node.names:
                if alias.name == "*":
                    continue
                info.import_candidates.add(alias.name)
                bound_name = alias.asname or alias.name
                _add_module_alias(info, bound_name, f"{node.module}.{alias.name}")

            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
            chain = _attribute_chain(node)
            if chain and len(chain) >= 2:
                info.attribute_chains.append(chain)
            self.generic_visit(node)

    Visitor().visit(tree)


def extract_file_info(
    file_path: Path, exclude_decorators: set[str] | None = None
) -> FileInfo | None:
    """Read a file once and extract all symbols and pragmas in a single pass."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError) as e:
        if isinstance(e, (SyntaxError, UnicodeDecodeError)):
            print(f"Warning: Could not parse {file_path}: {e}", file=sys.stderr)
        return None

    info = FileInfo(path=file_path, content=content)
    lines = content.splitlines()
    pragma_re = re.compile(r"^#\s*symvision:\s*(.+)$")
    _collect_usage_info(tree, info)

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        # Check decorator exclusion once
        if exclude_decorators and _get_decorator_names(node) & exclude_decorators:
            continue

        name = node.name

        if name.startswith("_"):
            info.private_symbols.append(name)
            info.private_def_lines[name] = node.lineno
        elif name != "main":
            info.public_symbols.append(name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates = _function_api_dependency_candidates(node)
            else:
                candidates = _class_api_dependency_candidates(node)
            candidates.discard(name)
            if candidates:
                info.api_dependency_candidates[name] = candidates

        # Extract pragmas for this symbol
        if node.decorator_list:
            start_line = node.decorator_list[0].lineno
        else:
            start_line = node.lineno

        comment_idx = start_line - 2
        if comment_idx < 0:
            continue

        symbol_pragmas: list[PragmaInfo] = []
        while comment_idx >= 0:
            m = pragma_re.match(lines[comment_idx].strip())
            if not m:
                break
            symbol_pragmas.append(
                PragmaInfo(
                    symbol_name=name,
                    ref_path=m.group(1).strip(),
                    source_file=file_path,
                    pragma_line=comment_idx + 1,
                )
            )
            comment_idx -= 1

        if symbol_pragmas:
            info.pragmas[name] = symbol_pragmas

    return info


def batch_search_usage(
    symbols: set[str],
    file_infos: list[FileInfo],
    tracked_modules: set[str] | None = None,
) -> set[str]:
    """Find which symbols are used by any file using pre-extracted AST info.

    Returns the set of symbols that are imported or referenced through a module
    alias by at least one file.
    """
    if not symbols:
        return set()

    found: set[str] = set()
    for info in file_infos:
        matches = symbols & info.import_candidates
        if matches:
            found |= matches
            if found == symbols:
                break  # All symbols found

        if tracked_modules:
            for chain in info.attribute_chains:
                symbol_name = chain[-1]
                if symbol_name not in symbols:
                    continue

                alias_modules = info.module_aliases.get(chain[0], set())
                for alias_module in alias_modules:
                    suffix = ".".join(chain[1:-1])
                    module_name = f"{alias_module}.{suffix}" if suffix else alias_module
                    if module_name in tracked_modules:
                        found.add(symbol_name)
                        break

                if found == symbols:
                    break

        if found == symbols:
            break
    return found


def batch_check_private_in_file(
    file_info: FileInfo,
) -> tuple[list[str], list[str]]:
    """Check all private symbols in a file for in-file usage.

    Returns (used_symbols, unused_symbols).
    """
    used = []
    unused = []
    lines = file_info.content.split("\n")
    for name in file_info.private_symbols:
        def_line = file_info.private_def_lines.get(name)
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        found = False
        for i, line in enumerate(lines, start=1):
            if i == def_line:
                continue
            if pattern.search(line):
                found = True
                break
        if found:
            used.append(name)
        else:
            unused.append(name)
    return used, unused

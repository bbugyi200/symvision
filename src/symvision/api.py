"""Public API dependency reachability."""

from symvision.models import FileInfo


def build_public_api_dependency_graph(
    file_infos: list[FileInfo], public_symbols: set[str]
) -> dict[str, set[str]]:
    """Build a conservative graph of explicit public API dependencies."""
    graph: dict[str, set[str]] = {}
    for info in file_infos:
        for symbol_name, candidates in info.api_dependency_candidates.items():
            dependencies = candidates & public_symbols
            dependencies.discard(symbol_name)
            if dependencies:
                graph.setdefault(symbol_name, set()).update(dependencies)
    return graph


def reachable_api_dependencies(roots: set[str], dependency_graph: dict[str, set[str]]) -> set[str]:
    """Return public API symbols reachable from externally proven roots."""
    reachable: set[str] = set()
    stack = list(roots)
    while stack:
        symbol_name = stack.pop()
        for dependency in dependency_graph.get(symbol_name, set()):
            if dependency in reachable or dependency in roots:
                continue
            reachable.add(dependency)
            stack.append(dependency)
    return reachable

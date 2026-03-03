"""Call graph from FORTRAN chunk metadata.

Builds a bidirectional call graph: for each program unit, tracks what it calls
and what calls it.
"""

import json
import logging
from pathlib import Path

from legacylens.ingest.chunker import FortranChunk

logger = logging.getLogger(__name__)

INDEX_PATH = Path("data/indices/call_graph.json")


def build_call_graph(chunks: list[FortranChunk]) -> dict:
    """Build a bidirectional call graph from chunks.

    Returns:
        dict mapping unit names to their call relationships:
        {"DCOMP": {"calls": [...], "called_by": [...], "file": ..., "line": ...}}
    """
    graph: dict[str, dict] = {}

    # First pass: register all known units and their outgoing calls
    for chunk in chunks:
        name = chunk.unit_name.upper()
        if not name:
            continue
        if name not in graph:
            graph[name] = {
                "calls": [],
                "called_by": [],
                "file": chunk.file_path,
                "line": chunk.line_start,
            }
        graph[name]["calls"] = sorted(set(c.upper() for c in chunk.calls))

    # Second pass: build called_by (reverse edges)
    # Iterate over a snapshot of items since we may add new keys
    for name, data in list(graph.items()):
        for callee in data["calls"]:
            if callee not in graph:
                graph[callee] = {
                    "calls": [],
                    "called_by": [],
                    "file": "",
                    "line": 0,
                }
            if name not in graph[callee]["called_by"]:
                graph[callee]["called_by"].append(name)

    # Sort called_by lists
    for name in graph:
        graph[name]["called_by"] = sorted(graph[name]["called_by"])

    logger.info(f"Built call graph: {len(graph)} nodes")
    return graph


def save_index(index: dict, path: Path | None = None) -> None:
    out = path or INDEX_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2))
    logger.info(f"Saved call graph to {out}")


def load_index(path: Path | None = None) -> dict:
    src = path or INDEX_PATH
    if not src.exists():
        return {}
    return json.loads(src.read_text())


def get_callers(unit_name: str, graph: dict | None = None) -> list[str]:
    """Who calls this unit?"""
    if graph is None:
        graph = load_index()
    entry = graph.get(unit_name.upper(), {})
    return entry.get("called_by", [])


def get_callees(unit_name: str, graph: dict | None = None) -> list[str]:
    """What does this unit call?"""
    if graph is None:
        graph = load_index()
    entry = graph.get(unit_name.upper(), {})
    return entry.get("calls", [])


def get_call_chain(unit_name: str, depth: int = 2, graph: dict | None = None) -> dict:
    """Get transitive call tree up to given depth.

    Returns:
        Nested dict: {"name": "DCOMP", "calls": [{"name": "XREAD", "calls": [...]}]}
    """
    if graph is None:
        graph = load_index()

    def _recurse(name: str, d: int, visited: set) -> dict:
        node: dict = {"name": name, "calls": []}
        if d <= 0 or name in visited:
            return node
        visited.add(name)
        for callee in get_callees(name, graph):
            child = _recurse(callee, d - 1, visited.copy())
            node["calls"].append(child)
        return node

    return _recurse(unit_name.upper(), depth, set())

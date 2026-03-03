"""Tests for call graph."""

from legacylens.ingest.chunker import FortranChunk
from legacylens.index.call_graph import (
    build_call_graph,
    get_call_chain,
    get_callees,
    get_callers,
)


def _make_chunk(name: str, calls: list[str], file: str = "test.f", line: int = 1) -> FortranChunk:
    return FortranChunk(
        text="",
        file_path=file,
        line_start=line,
        line_end=line + 10,
        unit_name=name,
        unit_type="subroutine",
        calls=calls,
    )


class TestBuildGraph:
    def test_simple_call(self):
        chunks = [
            _make_chunk("MAIN", ["INIT", "SOLVE"]),
            _make_chunk("INIT", []),
            _make_chunk("SOLVE", ["COMPUTE"]),
        ]
        graph = build_call_graph(chunks)
        assert "INIT" in graph["MAIN"]["calls"]
        assert "SOLVE" in graph["MAIN"]["calls"]
        assert "MAIN" in graph["INIT"]["called_by"]
        assert "MAIN" in graph["SOLVE"]["called_by"]

    def test_bidirectional(self):
        chunks = [
            _make_chunk("AAA", ["BBB"]),
            _make_chunk("BBB", ["CCC"]),
            _make_chunk("CCC", []),
        ]
        graph = build_call_graph(chunks)
        assert "BBB" in graph["AAA"]["calls"]
        assert "AAA" in graph["BBB"]["called_by"]
        assert "CCC" in graph["BBB"]["calls"]
        assert "BBB" in graph["CCC"]["called_by"]

    def test_unknown_callee(self):
        """Callees not in the codebase still appear in graph."""
        chunks = [_make_chunk("AAA", ["EXTERNAL_LIB"])]
        graph = build_call_graph(chunks)
        assert "EXTERNAL_LIB" in graph
        assert "AAA" in graph["EXTERNAL_LIB"]["called_by"]

    def test_empty(self):
        graph = build_call_graph([])
        assert graph == {}


class TestGetCallers:
    def test_callers(self):
        graph = {
            "AAA": {"calls": ["BBB"], "called_by": [], "file": "a.f", "line": 1},
            "BBB": {"calls": [], "called_by": ["AAA"], "file": "b.f", "line": 1},
        }
        assert get_callers("BBB", graph) == ["AAA"]

    def test_no_callers(self):
        graph = {
            "AAA": {"calls": [], "called_by": [], "file": "a.f", "line": 1},
        }
        assert get_callers("AAA", graph) == []


class TestGetCallees:
    def test_callees(self):
        graph = {
            "AAA": {"calls": ["BBB", "CCC"], "called_by": [], "file": "a.f", "line": 1},
        }
        assert get_callees("AAA", graph) == ["BBB", "CCC"]


class TestGetCallChain:
    def test_simple_chain(self):
        graph = {
            "AAA": {"calls": ["BBB"], "called_by": [], "file": "a.f", "line": 1},
            "BBB": {"calls": ["CCC"], "called_by": ["AAA"], "file": "b.f", "line": 1},
            "CCC": {"calls": [], "called_by": ["BBB"], "file": "c.f", "line": 1},
        }
        chain = get_call_chain("AAA", depth=2, graph=graph)
        assert chain["name"] == "AAA"
        assert len(chain["calls"]) == 1
        assert chain["calls"][0]["name"] == "BBB"
        assert len(chain["calls"][0]["calls"]) == 1
        assert chain["calls"][0]["calls"][0]["name"] == "CCC"

    def test_depth_limit(self):
        graph = {
            "AAA": {"calls": ["BBB"], "called_by": [], "file": "a.f", "line": 1},
            "BBB": {"calls": ["CCC"], "called_by": ["AAA"], "file": "b.f", "line": 1},
            "CCC": {"calls": ["DDD"], "called_by": ["BBB"], "file": "c.f", "line": 1},
            "DDD": {"calls": [], "called_by": ["CCC"], "file": "d.f", "line": 1},
        }
        chain = get_call_chain("AAA", depth=1, graph=graph)
        assert chain["name"] == "AAA"
        assert len(chain["calls"]) == 1
        assert chain["calls"][0]["name"] == "BBB"
        # At depth 1, BBB's calls should be empty (no further recursion)
        assert chain["calls"][0]["calls"] == []

    def test_cycle_detection(self):
        graph = {
            "AAA": {"calls": ["BBB"], "called_by": ["BBB"], "file": "a.f", "line": 1},
            "BBB": {"calls": ["AAA"], "called_by": ["AAA"], "file": "b.f", "line": 1},
        }
        # Should not infinite loop
        chain = get_call_chain("AAA", depth=5, graph=graph)
        assert chain["name"] == "AAA"

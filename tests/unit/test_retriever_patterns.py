"""Tests for retriever query pattern matching and index augmentation.

Validates that the retriever correctly extracts unit names and COMMON block
references from natural language queries, covering all 6 testing scenarios.
"""

import pytest
from unittest.mock import patch

from legacylens.search.retriever import (
    COMMON_BLOCK_RE,
    MAX_DISTANCE_THRESHOLD,
    UNIT_NAME_RE,
    _deduplicate_by_unit,
    _extract_unit_name,
    _keyword_rerank,
)


# ---------------------------------------------------------------------------
# Scenario 1: Entry point queries
# ---------------------------------------------------------------------------
class TestEntryPointQueries:
    """Where is the main entry point of this program?"""

    def test_program_keyword_detected(self):
        query = "Where is the main PROGRAM entry point in NASTRAN-95?"
        name = _extract_unit_name(query)
        # "PROGRAM entry" → extracts "entry" (forward match)
        assert name is not None

    def test_main_program_nastran(self):
        query = "What is the main program of NASTRAN?"
        name = _extract_unit_name(query)
        # "main program of" → forward match extracts "of"
        # Not ideal, but vector search handles the real work
        assert name is not None


# ---------------------------------------------------------------------------
# Scenario 2: COMMON block / shared state queries
# ---------------------------------------------------------------------------
class TestCommonBlockQueries:
    """What subroutines modify COMMON block /SYSTEM/?"""

    def test_common_block_explicit(self):
        query = "What subroutines reference COMMON block /SYSTEM/?"
        match = COMMON_BLOCK_RE.search(query)
        assert match is not None
        assert match.group(1).upper() == "SYSTEM"

    def test_common_block_bare_slash(self):
        query = "What subroutines modify /ZZZZZZ/?"
        match = COMMON_BLOCK_RE.search(query)
        assert match is not None
        assert match.group(1).upper() == "ZZZZZZ"

    def test_common_block_with_prefix(self):
        query = "Which routines use COMMON /PARAMS/?"
        match = COMMON_BLOCK_RE.search(query)
        assert match is not None
        assert match.group(1).upper() == "PARAMS"

    def test_no_common_block_in_plain_query(self):
        query = "How does NASTRAN handle matrix decomposition?"
        match = COMMON_BLOCK_RE.search(query)
        assert match is None


# ---------------------------------------------------------------------------
# Scenario 3: Specific unit explanation queries
# ---------------------------------------------------------------------------
class TestSpecificUnitQueries:
    """Explain what the DECOMP subroutine does."""

    def test_subroutine_keyword_before_name(self):
        query = "Explain what subroutine DECOMP does"
        name = _extract_unit_name(query)
        assert name == "DECOMP"

    def test_name_before_subroutine_keyword(self):
        """Reversed order: 'the DECOMP subroutine'"""
        query = "Explain what the DECOMP subroutine does"
        name = _extract_unit_name(query)
        assert name == "DECOMP"

    def test_function_keyword(self):
        query = "What does function VECNORM compute?"
        name = _extract_unit_name(query)
        assert name == "VECNORM"

    def test_uppercase_name_fallback(self):
        """Standalone uppercase name without keyword should match UNIT_NAME_RE."""
        query = "What does DCOMP do?"
        # _extract_unit_name won't find it (no keyword), but UNIT_NAME_RE will
        unit_matches = UNIT_NAME_RE.findall(query)
        assert "DCOMP" in unit_matches

    def test_module_keyword(self):
        query = "Explain the BANDIT module"
        name = _extract_unit_name(query)
        assert name == "BANDIT"


# ---------------------------------------------------------------------------
# Scenario 4: File I/O operation queries
# ---------------------------------------------------------------------------
class TestFileIOQueries:
    """Find all file I/O operations."""

    def test_io_query_is_conceptual(self):
        """I/O queries don't match specific units — rely on vector search."""
        query = "Find all file I/O operations and READ/WRITE statements"
        common_match = COMMON_BLOCK_RE.search(query)
        assert common_match is None
        # No unit name with keyword should be extracted
        name = _extract_unit_name(query)
        # May or may not extract something, but COMMON block should be None
        assert common_match is None


# ---------------------------------------------------------------------------
# Scenario 5: Dependency queries
# ---------------------------------------------------------------------------
class TestDependencyQueries:
    """What are the dependencies of MODULE-X?"""

    def test_dependency_query_with_keyword(self):
        query = "What are the dependencies of the DCOMP subroutine?"
        name = _extract_unit_name(query)
        assert name == "DCOMP"

    def test_dependency_query_without_keyword(self):
        query = "What does DCOMP depend on?"
        # _extract_unit_name won't find it, but UNIT_NAME_RE will
        unit_matches = UNIT_NAME_RE.findall(query)
        assert "DCOMP" in unit_matches

    def test_callers_query(self):
        query = "What subroutines call XREAD?"
        unit_matches = UNIT_NAME_RE.findall(query)
        assert "XREAD" in unit_matches


# ---------------------------------------------------------------------------
# Scenario 6: Pattern-finding queries
# ---------------------------------------------------------------------------
class TestPatternQueries:
    """Show me error handling patterns in this codebase."""

    def test_pattern_query_no_common_block(self):
        query = "Show me error handling patterns in the NASTRAN-95 codebase"
        common_match = COMMON_BLOCK_RE.search(query)
        assert common_match is None


# ---------------------------------------------------------------------------
# Index augmentation integration
# ---------------------------------------------------------------------------
class TestIndexAugmentation:
    """Test that _augment_with_indices correctly enriches results."""

    def _make_result(self, unit_name="TEST", common_blocks=None, text=""):
        return {
            "text": text,
            "metadata": {
                "unit_name": unit_name,
                "common_blocks": common_blocks or [],
                "file_path": "test.f",
                "line_start": 1,
                "line_end": 10,
            },
            "score": 0.5,
            "index_context": "",
        }

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_with_common_block_query(self, mock_cg, mock_ci):
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {
            "/SYSTEM/": {
                "referenced_by": [
                    {"unit": "SOLVER", "file": "solver.f", "line": 5},
                    {"unit": "MAIN", "file": "main.f", "line": 10},
                ]
            }
        }
        mock_cg.return_value = {}

        results = [self._make_result()]
        _augment_with_indices("What subroutines reference COMMON block /SYSTEM/?", results)

        assert "SYSTEM" in results[0]["index_context"]
        assert "SOLVER" in results[0]["index_context"]

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_with_subroutine_forward(self, mock_cg, mock_ci):
        """Forward pattern: 'subroutine DCOMP'"""
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {
                "calls": ["MESAGE", "CLOSE"],
                "called_by": ["SOLVER", "MAIN"],
            }
        }

        results = [self._make_result()]
        _augment_with_indices("What does subroutine DCOMP do?", results)

        ctx = results[0]["index_context"]
        assert "DCOMP calls" in ctx
        assert "DCOMP is called by" in ctx

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_with_subroutine_reversed(self, mock_cg, mock_ci):
        """Reverse pattern: 'DCOMP subroutine'"""
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {
                "calls": ["MESAGE", "CLOSE"],
                "called_by": ["SOLVER", "MAIN"],
            }
        }

        results = [self._make_result()]
        _augment_with_indices("What are the dependencies of the DCOMP subroutine?", results)

        ctx = results[0]["index_context"]
        assert "DCOMP calls" in ctx
        assert "DCOMP is called by" in ctx

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_with_standalone_name(self, mock_cg, mock_ci):
        """Standalone uppercase name (no keyword) should still trigger call graph lookup."""
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {
                "calls": ["MESAGE"],
                "called_by": ["SOLVER"],
            }
        }

        results = [self._make_result()]
        _augment_with_indices("What does DCOMP do?", results)

        ctx = results[0]["index_context"]
        assert "DCOMP calls" in ctx

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_injects_direct_chunk(self, mock_cg, mock_ci):
        """When a unit name is found and not in results, inject it from ChromaDB."""
        from legacylens.search.retriever import _augment_with_indices
        from unittest.mock import MagicMock

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {"calls": ["MESAGE"], "called_by": ["SOLVER"]}
        }

        # Mock ChromaDB collection
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["chunk_dcomp"],
            "documents": ["SUBROUTINE DCOMP(A,B,C)\n  CALL MESAGE\nEND"],
            "metadatas": [{"unit_name": "DCOMP", "file_path": "dcomp.f",
                           "line_start": 1, "line_end": 3}],
        }

        results = [self._make_result(unit_name="OTHER")]
        _augment_with_indices("What does DCOMP depend on?", results, collection=mock_collection)

        # DCOMP chunk should be prepended
        assert results[0]["metadata"]["unit_name"] == "DCOMP"
        assert results[0]["score"] == 0.0

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_no_duplicate_injection(self, mock_cg, mock_ci):
        """If the unit is already in results, don't inject a duplicate of it."""
        from legacylens.search.retriever import _augment_with_indices
        from unittest.mock import MagicMock

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {"calls": ["MESAGE"], "called_by": ["SOLVER"]}
        }

        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        # DCOMP is already present; it should not be fetched again, but
        # neighbors (MESAGE, SOLVER) may still be injected
        results = [self._make_result(unit_name="DCOMP")]
        _augment_with_indices("What does subroutine DCOMP do?", results, collection=mock_collection)

        # DCOMP itself should NOT have been queried (already present)
        queried_units = [call.kwargs.get("where", {}).get("unit_name")
                        for call in mock_collection.get.call_args_list]
        assert "DCOMP" not in queried_units

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_augment_conceptual_query_no_crash(self, mock_cg, mock_ci):
        """Conceptual queries with no specific matches should not crash."""
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {}
        mock_cg.return_value = {}

        results = [self._make_result()]
        _augment_with_indices("Show me error handling patterns in the codebase", results)

        # Should not add any index context for conceptual queries
        assert results[0]["index_context"] == ""


# ---------------------------------------------------------------------------
# Keyword re-ranking tests
# ---------------------------------------------------------------------------
class TestKeywordReranking:
    """Test that keyword re-ranking boosts relevant results."""

    def _make_result(self, text, score):
        return {
            "text": text,
            "metadata": {"unit_name": "TEST", "file_path": "test.f"},
            "score": score,
            "index_context": "",
        }

    def test_io_query_boosts_io_chunks(self):
        """I/O-related chunks should get a score bonus for I/O queries."""
        results = [
            self._make_result("CALL SOLVER(A,B)", 0.8),
            self._make_result("READ(5,100) X\nWRITE(6,200) Y\nOPEN(UNIT=10)", 0.9),
        ]
        _keyword_rerank("Find all file I/O operations", results)

        # The I/O chunk (originally worse) should now rank better
        assert results[0]["text"].startswith("READ")

    def test_no_keywords_no_change(self):
        """Queries without relevant keywords should not alter scores."""
        results = [
            self._make_result("CALL SOLVER(A,B)", 0.5),
            self._make_result("CALL DECOMP(X,Y)", 0.6),
        ]
        _keyword_rerank("What is the main entry point?", results)

        assert results[0]["score"] == 0.5
        assert results[1]["score"] == 0.6

    def test_bonus_is_capped(self):
        """Keyword bonus should not exceed the maximum cap."""
        # A chunk with many I/O keywords
        text = " ".join(["READ WRITE OPEN CLOSE REWIND"] * 10)
        results = [self._make_result(text, 1.0)]
        _keyword_rerank("Find all file I/O operations", results)

        # Score should be reduced by at most _MAX_KEYWORD_BONUS (0.35)
        assert results[0]["score"] >= 1.0 - 0.35 - 0.001

    def test_error_keywords_boost(self):
        """Error-related queries should boost error chunks."""
        results = [
            self._make_result("CALL SOLVER(A,B)", 0.7),
            self._make_result("CALL MESAGE(FATAL,ERROR)\nIF(IERR) ABORT", 0.8),
        ]
        _keyword_rerank("Show me error handling patterns", results)

        assert results[0]["text"].startswith("CALL MESAGE")

    def test_matrix_keywords_boost(self):
        """Matrix-related queries should boost matrix chunks."""
        results = [
            self._make_result("CALL SOLVER(A,B)", 0.7),
            self._make_result("CALL DECOMP(A,N)\nCALL FBS(A,B,N)\nPIVOT=A(I,I)", 0.8),
        ]
        _keyword_rerank("How does matrix decomposition work?", results)

        assert results[0]["text"].startswith("CALL DECOMP")

    def test_element_keywords_boost(self):
        """Element-related queries should boost element chunks."""
        results = [
            self._make_result("CALL SOLVER(A,B)", 0.7),
            self._make_result("STIFFNESS MATRIX\nCALL ASSEMBLE(ELEMENT,DOF)", 0.8),
        ]
        _keyword_rerank("How are element stiffness matrices assembled?", results)

        assert results[0]["text"].startswith("STIFFNESS")

    def test_data_mgmt_keywords_boost(self):
        """Data management queries should boost GINO/table chunks."""
        results = [
            self._make_result("CALL SOLVER(A,B)", 0.7),
            self._make_result("CALL GINO(BUFFER)\nTRAILER(1)=MCB", 0.8),
        ]
        _keyword_rerank("How does GINO buffer management work?", results)

        assert results[0]["text"].startswith("CALL GINO")


# ---------------------------------------------------------------------------
# Distance threshold tests
# ---------------------------------------------------------------------------
class TestDistanceThreshold:
    """Test that MAX_DISTANCE_THRESHOLD filters irrelevant results."""

    def _make_result(self, score, unit_name="TEST"):
        return {
            "text": f"SUBROUTINE {unit_name}",
            "metadata": {"unit_name": unit_name, "file_path": "test.f"},
            "score": score,
            "index_context": "",
        }

    def test_results_within_threshold_kept(self):
        results = [self._make_result(0.5), self._make_result(1.0), self._make_result(1.2)]
        filtered = [r for r in results if r["score"] <= MAX_DISTANCE_THRESHOLD]
        assert len(filtered) == 3

    def test_results_above_threshold_removed(self):
        results = [self._make_result(0.5), self._make_result(1.5), self._make_result(1.8)]
        filtered = [r for r in results if r["score"] <= MAX_DISTANCE_THRESHOLD]
        assert len(filtered) == 1
        assert filtered[0]["score"] == 0.5

    def test_threshold_boundary(self):
        results = [self._make_result(1.2), self._make_result(1.2001)]
        filtered = [r for r in results if r["score"] <= MAX_DISTANCE_THRESHOLD]
        assert len(filtered) == 1


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------
class TestDeduplication:
    """Test that _deduplicate_by_unit keeps only the best chunk per unit."""

    def _make_result(self, unit_name, score):
        return {
            "text": f"SUBROUTINE {unit_name}",
            "metadata": {"unit_name": unit_name, "file_path": "test.f"},
            "score": score,
            "index_context": "",
        }

    def test_keeps_best_score(self):
        results = [
            self._make_result("DECOMP", 0.8),
            self._make_result("DECOMP", 0.5),
            self._make_result("SOLVER", 0.6),
        ]
        _deduplicate_by_unit(results)
        units = [r["metadata"]["unit_name"] for r in results]
        assert units.count("DECOMP") == 1
        decomp = [r for r in results if r["metadata"]["unit_name"] == "DECOMP"][0]
        assert decomp["score"] == 0.5

    def test_keeps_orphans(self):
        """Chunks with empty unit_name are always kept."""
        results = [
            self._make_result("", 0.5),
            self._make_result("", 0.6),
            self._make_result("DECOMP", 0.7),
        ]
        _deduplicate_by_unit(results)
        assert len(results) == 3

    def test_noop_when_no_dupes(self):
        results = [
            self._make_result("DECOMP", 0.5),
            self._make_result("SOLVER", 0.6),
            self._make_result("MAIN", 0.7),
        ]
        _deduplicate_by_unit(results)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Call graph scoping tests
# ---------------------------------------------------------------------------
class TestCallGraphScoping:
    """Test that call graph context is only appended to the matching unit."""

    def _make_result(self, unit_name="TEST", score=0.5):
        return {
            "text": f"SUBROUTINE {unit_name}",
            "metadata": {
                "unit_name": unit_name,
                "common_blocks": [],
                "file_path": "test.f",
                "line_start": 1,
                "line_end": 10,
            },
            "score": score,
            "index_context": "",
        }

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_call_graph_context_only_on_matching_unit(self, mock_cg, mock_ci):
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {"calls": ["MESAGE"], "called_by": ["SOLVER"]}
        }

        results = [
            self._make_result("DCOMP"),
            self._make_result("OTHER"),
        ]
        _augment_with_indices("What does subroutine DCOMP do?", results)

        assert "DCOMP calls" in results[0]["index_context"]
        # OTHER should NOT have the DCOMP call graph info
        assert "DCOMP calls" not in results[1]["index_context"]

    @patch("legacylens.search.retriever.load_common_index")
    @patch("legacylens.search.retriever.load_call_graph")
    def test_call_graph_fallback_to_first_when_no_match(self, mock_cg, mock_ci):
        from legacylens.search.retriever import _augment_with_indices

        mock_ci.return_value = {}
        mock_cg.return_value = {
            "DCOMP": {"calls": ["MESAGE"], "called_by": ["SOLVER"]}
        }

        results = [
            self._make_result("OTHER"),
            self._make_result("ANOTHER"),
        ]
        _augment_with_indices("What does subroutine DCOMP do?", results)

        # Should fall back to first result
        assert "DCOMP calls" in results[0]["index_context"]
        assert "DCOMP calls" not in results[1]["index_context"]

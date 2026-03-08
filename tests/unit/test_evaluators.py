"""Tests for the evaluation suite."""

import pytest
from evals.evaluators import (
    keyword_coverage,
    unit_mention_check,
    answer_length_check,
    code_reference_check,
    fortran_syntax_check,
    call_graph_context_check,
    no_hallucination_check,
    evaluate_rag_output,
)


class TestKeywordCoverage:
    """Tests for keyword_coverage evaluator."""

    def test_all_keywords_found(self):
        result = keyword_coverage(
            output="The matrix decomposition uses factorization",
            expected_keywords=["matrix", "decomposition", "factor"]
        )
        assert result.score == 1.0
        assert result.key == "keyword_coverage"

    def test_partial_keywords_found(self):
        result = keyword_coverage(
            output="The matrix operation is complex",
            expected_keywords=["matrix", "decomposition", "factor"]
        )
        assert result.score == pytest.approx(1/3)

    def test_no_keywords_found(self):
        result = keyword_coverage(
            output="This is unrelated content",
            expected_keywords=["matrix", "decomposition"]
        )
        assert result.score == 0.0

    def test_case_insensitive(self):
        result = keyword_coverage(
            output="The MATRIX uses DECOMPOSITION",
            expected_keywords=["matrix", "decomposition"]
        )
        assert result.score == 1.0

    def test_empty_keywords(self):
        result = keyword_coverage(
            output="Some output",
            expected_keywords=[]
        )
        assert result.score is None


class TestUnitMentionCheck:
    """Tests for unit_mention_check evaluator."""

    def test_unit_found(self):
        result = unit_mention_check(
            output="The DECOMP subroutine performs factorization",
            expected_unit="DECOMP"
        )
        assert result.score == 1

    def test_unit_not_found(self):
        result = unit_mention_check(
            output="The subroutine performs factorization",
            expected_unit="DECOMP"
        )
        assert result.score == 0

    def test_case_insensitive(self):
        result = unit_mention_check(
            output="The decomp subroutine works well",
            expected_unit="DECOMP"
        )
        assert result.score == 1

    def test_no_expected_unit(self):
        result = unit_mention_check(
            output="Some output",
            expected_unit=None
        )
        assert result.score is None


class TestAnswerLengthCheck:
    """Tests for answer_length_check evaluator."""

    def test_within_bounds(self):
        output = " ".join(["word"] * 50)
        result = answer_length_check(output, min_words=20, max_words=100)
        assert result.score == 1

    def test_too_short(self):
        output = "Too short"
        result = answer_length_check(output, min_words=20)
        assert result.score == 0

    def test_too_long(self):
        output = " ".join(["word"] * 600)
        result = answer_length_check(output, max_words=500)
        assert result.score == 0


class TestCodeReferenceCheck:
    """Tests for code_reference_check evaluator."""

    def test_file_reference_found(self):
        result = code_reference_check("See the code in solver.f for details")
        assert result.score == 1

    def test_line_reference_found(self):
        result = code_reference_check("The error occurs at line 42")
        assert result.score == 1

    def test_no_references(self):
        result = code_reference_check("This is a general explanation")
        assert result.score == 0


class TestFortranSyntaxCheck:
    """Tests for fortran_syntax_check evaluator."""

    def test_many_fortran_terms(self):
        output = "The SUBROUTINE uses COMMON blocks and DIMENSION arrays with DO loops"
        result = fortran_syntax_check(output)
        assert result.score >= 0.6

    def test_few_fortran_terms(self):
        output = "The function calls another subroutine"
        result = fortran_syntax_check(output)
        assert result.score <= 0.6

    def test_no_fortran_terms(self):
        output = "This is a generic programming description"
        result = fortran_syntax_check(output)
        assert result.score == 0.0


class TestCallGraphContextCheck:
    """Tests for call_graph_context_check evaluator."""

    def test_calls_mentioned(self):
        result = call_graph_context_check("DECOMP calls MESAGE and CLOSE")
        assert result.score == 1

    def test_called_by_mentioned(self):
        result = call_graph_context_check("This routine is called by SOLVER")
        assert result.score == 1

    def test_no_call_context(self):
        result = call_graph_context_check("This routine performs calculations")
        assert result.score == 0


class TestNoHallucinationCheck:
    """Tests for no_hallucination_check evaluator."""

    def test_confident_answer(self):
        result = no_hallucination_check(
            "The DECOMP subroutine performs LU factorization on the stiffness matrix."
        )
        assert result.score == 1

    def test_hedging_detected(self):
        result = no_hallucination_check(
            "I don't have access to that specific information about the code."
        )
        assert result.score == 0

    def test_uncertainty_detected(self):
        result = no_hallucination_check(
            "I'm not sure what this subroutine does exactly."
        )
        assert result.score == 0


class TestCompositeEvaluator:
    """Tests for evaluate_rag_output composite evaluator."""

    def test_basic_evaluation(self):
        golden = {
            "expected_answer_contains": ["matrix", "factor"],
            "expected_unit_mentioned": "DECOMP",
            "category": "unit_explanation",
        }
        output = "The DECOMP subroutine performs matrix factorization in solver.f"

        results = evaluate_rag_output(output, golden)

        # Should have multiple evaluators
        assert len(results) >= 4

        # Check specific results
        keys = [r.key for r in results]
        assert "keyword_coverage" in keys
        assert "unit_mention" in keys
        assert "answer_length" in keys

    def test_dependency_category(self):
        golden = {
            "expected_mentions_call_graph": True,
            "category": "dependency_analysis",
        }
        output = "DECOMP calls MESAGE and is called by SOLVER"

        results = evaluate_rag_output(output, golden)

        keys = [r.key for r in results]
        assert "call_graph_context" in keys
        assert "code_reference" in keys

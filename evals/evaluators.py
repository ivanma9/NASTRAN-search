"""Evaluators for LegacyLens RAG system.

These evaluators assess LLM output quality against golden datasets.
Can be used standalone or with LangSmith experiments.
"""

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    """Result of a single evaluation."""
    key: str
    score: float | int | bool | None
    comment: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "score": self.score, "comment": self.comment}


# ---------------------------------------------------------------------------
# Output Quality Evaluators
# ---------------------------------------------------------------------------

def keyword_coverage(
    output: str,
    expected_keywords: list[str],
) -> EvalResult:
    """Check if the output contains expected keywords.

    Args:
        output: The LLM-generated answer
        expected_keywords: List of keywords that should appear in the output

    Returns:
        EvalResult with score as fraction of keywords found (0.0 to 1.0)
    """
    if not expected_keywords:
        return EvalResult(
            key="keyword_coverage",
            score=None,
            comment="No expected keywords provided"
        )

    output_lower = output.lower()
    found = sum(1 for kw in expected_keywords if kw.lower() in output_lower)
    score = found / len(expected_keywords)

    missing = [kw for kw in expected_keywords if kw.lower() not in output_lower]
    comment = f"Found {found}/{len(expected_keywords)} keywords"
    if missing:
        comment += f". Missing: {missing}"

    return EvalResult(key="keyword_coverage", score=score, comment=comment)


def unit_mention_check(
    output: str,
    expected_unit: str | None,
) -> EvalResult:
    """Check if the output mentions the expected unit/subroutine name.

    Args:
        output: The LLM-generated answer
        expected_unit: The unit name that should be mentioned

    Returns:
        EvalResult with binary score (1 if found, 0 if not)
    """
    if not expected_unit:
        return EvalResult(
            key="unit_mention",
            score=None,
            comment="No expected unit specified"
        )

    # Check for the unit name (case-insensitive)
    pattern = re.compile(rf"\b{re.escape(expected_unit)}\b", re.IGNORECASE)
    found = bool(pattern.search(output))

    return EvalResult(
        key="unit_mention",
        score=1 if found else 0,
        comment=f"Unit '{expected_unit}' {'found' if found else 'not found'} in output"
    )


def answer_length_check(
    output: str,
    min_words: int = 20,
    max_words: int = 500,
) -> EvalResult:
    """Check if the answer length is within acceptable bounds.

    Args:
        output: The LLM-generated answer
        min_words: Minimum acceptable word count
        max_words: Maximum acceptable word count

    Returns:
        EvalResult with binary score (1 if within bounds, 0 if not)
    """
    word_count = len(output.split())
    in_bounds = min_words <= word_count <= max_words

    return EvalResult(
        key="answer_length",
        score=1 if in_bounds else 0,
        comment=f"Word count: {word_count} (expected {min_words}-{max_words})"
    )


def code_reference_check(output: str) -> EvalResult:
    """Check if the output contains code references (file paths, line numbers).

    For a RAG system over code, good answers should reference specific locations.

    Args:
        output: The LLM-generated answer

    Returns:
        EvalResult with binary score (1 if references found, 0 if not)
    """
    # Look for file paths or line references
    file_pattern = r"\b[\w/]+\.(f|f90|for|F|F90)\b"
    line_pattern = r"\b(line|lines?)\s*\d+"

    has_file_ref = bool(re.search(file_pattern, output, re.IGNORECASE))
    has_line_ref = bool(re.search(line_pattern, output, re.IGNORECASE))

    score = 1 if (has_file_ref or has_line_ref) else 0
    refs_found = []
    if has_file_ref:
        refs_found.append("file paths")
    if has_line_ref:
        refs_found.append("line numbers")

    return EvalResult(
        key="code_reference",
        score=score,
        comment=f"References found: {refs_found}" if refs_found else "No code references found"
    )


def fortran_syntax_check(output: str) -> EvalResult:
    """Check if the output contains FORTRAN-specific terminology.

    Good answers about FORTRAN code should use appropriate terminology.

    Args:
        output: The LLM-generated answer

    Returns:
        EvalResult with score based on FORTRAN term density
    """
    fortran_terms = [
        "subroutine", "function", "common", "dimension", "call",
        "integer", "real", "double precision", "character",
        "do loop", "if then", "end if", "continue", "goto",
        "format", "read", "write", "open", "close"
    ]

    output_lower = output.lower()
    found = sum(1 for term in fortran_terms if term in output_lower)

    # Score: at least 2 terms = good, normalized to max of 5
    score = min(found / 5.0, 1.0) if found >= 2 else found / 5.0

    return EvalResult(
        key="fortran_terminology",
        score=score,
        comment=f"Found {found} FORTRAN-specific terms"
    )


def call_graph_context_check(output: str) -> EvalResult:
    """Check if the output discusses call relationships.

    For dependency queries, the answer should mention callers/callees.

    Args:
        output: The LLM-generated answer

    Returns:
        EvalResult with binary score
    """
    call_terms = ["calls", "called by", "depends on", "dependency", "invokes", "invoked by"]
    output_lower = output.lower()

    found = any(term in output_lower for term in call_terms)

    return EvalResult(
        key="call_graph_context",
        score=1 if found else 0,
        comment="Call relationship context present" if found else "No call relationship context"
    )


def no_hallucination_check(output: str) -> EvalResult:
    """Basic check for potential hallucination indicators.

    Flags answers that hedge too much or admit uncertainty excessively.
    Note: This is a heuristic, not a definitive hallucination detector.

    Args:
        output: The LLM-generated answer

    Returns:
        EvalResult with score (1 = confident, 0 = hedging detected)
    """
    hedge_phrases = [
        "i don't have access",
        "i cannot find",
        "i'm not sure",
        "i don't know",
        "unable to determine",
        "no information available",
        "cannot be determined",
    ]

    output_lower = output.lower()
    hedging = any(phrase in output_lower for phrase in hedge_phrases)

    return EvalResult(
        key="confidence",
        score=0 if hedging else 1,
        comment="Hedging/uncertainty detected" if hedging else "Answer appears confident"
    )


# ---------------------------------------------------------------------------
# Composite Evaluator
# ---------------------------------------------------------------------------

def evaluate_rag_output(
    output: str,
    golden_example: dict,
) -> list[EvalResult]:
    """Run all relevant evaluators on a RAG output.

    Args:
        output: The LLM-generated answer
        golden_example: Dict with expected values from golden dataset

    Returns:
        List of EvalResult objects
    """
    results = []

    # Always run these
    results.append(answer_length_check(output))
    results.append(no_hallucination_check(output))
    results.append(fortran_syntax_check(output))

    # Conditional evaluators based on golden example fields
    if "expected_answer_contains" in golden_example:
        results.append(keyword_coverage(output, golden_example["expected_answer_contains"]))

    if "expected_unit_mentioned" in golden_example:
        results.append(unit_mention_check(output, golden_example["expected_unit_mentioned"]))

    if golden_example.get("expected_mentions_call_graph"):
        results.append(call_graph_context_check(output))

    if golden_example.get("category") in ["unit_explanation", "dependency_analysis"]:
        results.append(code_reference_check(output))

    return results


# ---------------------------------------------------------------------------
# LangSmith-compatible evaluator wrappers
# ---------------------------------------------------------------------------

def langsmith_keyword_coverage(run, example) -> dict:
    """LangSmith-compatible wrapper for keyword_coverage.

    Expects:
        - run.outputs["answer"]: The LLM output
        - example.metadata["expected_answer_contains"]: List of keywords
    """
    output = run.outputs.get("answer", "") if run.outputs else ""
    expected = example.metadata.get("expected_answer_contains", []) if example.metadata else []

    result = keyword_coverage(output, expected)
    return result.to_dict()


def langsmith_unit_mention(run, example) -> dict:
    """LangSmith-compatible wrapper for unit_mention_check."""
    output = run.outputs.get("answer", "") if run.outputs else ""
    expected_unit = example.metadata.get("expected_unit_mentioned") if example.metadata else None

    result = unit_mention_check(output, expected_unit)
    return result.to_dict()


def langsmith_answer_quality(run, example) -> list[dict]:
    """LangSmith-compatible composite evaluator.

    Returns multiple metrics in a single evaluator.
    """
    output = run.outputs.get("answer", "") if run.outputs else ""

    results = [
        answer_length_check(output),
        no_hallucination_check(output),
        fortran_syntax_check(output),
    ]

    return [r.to_dict() for r in results]


# ---------------------------------------------------------------------------
# Summary Evaluators (for experiment-level metrics)
# ---------------------------------------------------------------------------

def summary_pass_rate(runs: list, examples: list) -> dict:
    """Calculate overall pass rate across all examples.

    An example "passes" if keyword_coverage >= 0.5.
    """
    if not runs:
        return {"key": "pass_rate", "score": None, "comment": "No runs to evaluate"}

    passed = 0
    for run, example in zip(runs, examples):
        output = run.outputs.get("answer", "") if run.outputs else ""
        expected = example.metadata.get("expected_answer_contains", []) if example.metadata else []

        if expected:
            result = keyword_coverage(output, expected)
            if result.score and result.score >= 0.5:
                passed += 1
        else:
            passed += 1  # No keywords = automatic pass

    rate = passed / len(runs)
    return {
        "key": "pass_rate",
        "score": rate,
        "comment": f"{passed}/{len(runs)} examples passed"
    }


def summary_avg_keyword_coverage(runs: list, examples: list) -> dict:
    """Calculate average keyword coverage across all examples."""
    if not runs:
        return {"key": "avg_keyword_coverage", "score": None, "comment": "No runs"}

    scores = []
    for run, example in zip(runs, examples):
        output = run.outputs.get("answer", "") if run.outputs else ""
        expected = example.metadata.get("expected_answer_contains", []) if example.metadata else []

        if expected:
            result = keyword_coverage(output, expected)
            if result.score is not None:
                scores.append(result.score)

    if not scores:
        return {"key": "avg_keyword_coverage", "score": None, "comment": "No applicable examples"}

    avg = sum(scores) / len(scores)
    return {
        "key": "avg_keyword_coverage",
        "score": avg,
        "comment": f"Average over {len(scores)} examples"
    }

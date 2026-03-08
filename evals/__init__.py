"""LegacyLens evaluation suite for RAG quality assessment."""

from evals.evaluators import (
    EvalResult,
    keyword_coverage,
    unit_mention_check,
    answer_length_check,
    code_reference_check,
    fortran_syntax_check,
    call_graph_context_check,
    no_hallucination_check,
    evaluate_rag_output,
    # LangSmith wrappers
    langsmith_keyword_coverage,
    langsmith_unit_mention,
    langsmith_answer_quality,
    summary_pass_rate,
    summary_avg_keyword_coverage,
)

__all__ = [
    "EvalResult",
    "keyword_coverage",
    "unit_mention_check",
    "answer_length_check",
    "code_reference_check",
    "fortran_syntax_check",
    "call_graph_context_check",
    "no_hallucination_check",
    "evaluate_rag_output",
    "langsmith_keyword_coverage",
    "langsmith_unit_mention",
    "langsmith_answer_quality",
    "summary_pass_rate",
    "summary_avg_keyword_coverage",
]

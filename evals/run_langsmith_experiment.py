#!/usr/bin/env python
"""Run LangSmith experiments for LegacyLens RAG evaluation.

Prerequisites:
    - LANGSMITH_API_KEY environment variable set
    - Dataset uploaded to LangSmith (use upload_dataset.py first)

Usage:
    uv run python evals/run_langsmith_experiment.py --dataset legacylens-golden
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from langsmith import evaluate
from langsmith.schemas import Run, Example

from legacylens.search.retriever import retrieve
from legacylens.search.context import assemble_context
from legacylens.search.generator import generate_answer
from evals.evaluators import (
    langsmith_keyword_coverage,
    langsmith_unit_mention,
    langsmith_answer_quality,
    summary_pass_rate,
    summary_avg_keyword_coverage,
)


def target(inputs: dict) -> dict:
    """Target function that runs the RAG pipeline.

    Args:
        inputs: Dict with 'question' key from dataset

    Returns:
        Dict with 'answer' key containing the LLM response
    """
    question = inputs["question"]

    # Run RAG pipeline
    results = retrieve(question)
    context = assemble_context(results)
    answer = generate_answer(question, context)

    return {
        "answer": answer,
        "retrieved_chunks": len(results),
    }


def run_experiment(
    dataset_name: str,
    experiment_prefix: str = "legacylens-eval",
    max_concurrency: int = 2,
) -> None:
    """Run a LangSmith evaluation experiment.

    Args:
        dataset_name: Name of the LangSmith dataset
        experiment_prefix: Prefix for the experiment name
        max_concurrency: Max parallel evaluations
    """
    print(f"Running experiment on dataset: {dataset_name}")
    print(f"Experiment prefix: {experiment_prefix}")

    results = evaluate(
        target,
        data=dataset_name,
        evaluators=[
            langsmith_keyword_coverage,
            langsmith_unit_mention,
            langsmith_answer_quality,
        ],
        summary_evaluators=[
            summary_pass_rate,
            summary_avg_keyword_coverage,
        ],
        experiment_prefix=experiment_prefix,
        max_concurrency=max_concurrency,
    )

    print("\nExperiment complete!")
    print(f"View results at: https://smith.langchain.com")


def main():
    parser = argparse.ArgumentParser(description="Run LangSmith RAG experiments")
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="LangSmith dataset name",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="legacylens-eval",
        help="Experiment name prefix",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Max concurrent evaluations",
    )

    args = parser.parse_args()

    run_experiment(
        dataset_name=args.dataset,
        experiment_prefix=args.prefix,
        max_concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()

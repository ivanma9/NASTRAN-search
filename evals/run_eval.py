#!/usr/bin/env python
"""Run evaluations on the LegacyLens RAG system.

Usage:
    # Run against golden dataset (local, no LangSmith required)
    uv run python evals/run_eval.py --dataset evals/golden_dataset.json

    # Run specific examples
    uv run python evals/run_eval.py --dataset evals/golden_dataset.json --ids golden_001 golden_002

    # Output results to JSON
    uv run python evals/run_eval.py --dataset evals/golden_dataset.json --output results.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root and evals to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from legacylens.search.retriever import retrieve
from legacylens.search.context import assemble_context
from legacylens.search.generator import generate_answer
from evals.evaluators import evaluate_rag_output, EvalResult


def run_rag_pipeline(question: str) -> dict:
    """Run the full RAG pipeline and return results."""
    # Retrieve relevant chunks
    results = retrieve(question)

    # Assemble context
    context = assemble_context(results)

    # Generate answer
    answer = generate_answer(question, context)

    return {
        "question": question,
        "answer": answer,
        "retrieved_chunks": len(results),
        "context_length": len(context),
    }


def run_evaluation(
    dataset_path: str,
    example_ids: list[str] | None = None,
    verbose: bool = True,
) -> dict:
    """Run evaluation on a dataset.

    Args:
        dataset_path: Path to golden or labeled dataset JSON
        example_ids: Optional list of specific example IDs to run
        verbose: Whether to print progress

    Returns:
        Dict with evaluation results and summary statistics
    """
    with open(dataset_path) as f:
        dataset = json.load(f)

    # Filter to specific IDs if requested
    if example_ids:
        dataset = [ex for ex in dataset if ex["id"] in example_ids]
        if not dataset:
            raise ValueError(f"No examples found with IDs: {example_ids}")

    results = []
    all_scores = {}

    for i, example in enumerate(dataset):
        if verbose:
            print(f"\n[{i+1}/{len(dataset)}] Evaluating: {example['id']}")
            print(f"  Question: {example['question'][:60]}...")

        try:
            # Run RAG pipeline
            rag_output = run_rag_pipeline(example["question"])

            # Run evaluators
            eval_results = evaluate_rag_output(rag_output["answer"], example)

            # Collect scores
            example_result = {
                "id": example["id"],
                "question": example["question"],
                "answer": rag_output["answer"],
                "retrieved_chunks": rag_output["retrieved_chunks"],
                "evaluations": [r.to_dict() for r in eval_results],
                "error": None,
            }

            # Track scores for summary
            for r in eval_results:
                if r.score is not None:
                    if r.key not in all_scores:
                        all_scores[r.key] = []
                    all_scores[r.key].append(r.score)

            if verbose:
                for r in eval_results:
                    status = "✓" if r.score and r.score >= 0.5 else "✗" if r.score == 0 else "~"
                    score_str = f"{r.score:.2f}" if isinstance(r.score, float) else str(r.score)
                    print(f"  {status} {r.key}: {score_str} - {r.comment}")

        except Exception as e:
            example_result = {
                "id": example["id"],
                "question": example["question"],
                "answer": None,
                "retrieved_chunks": 0,
                "evaluations": [],
                "error": str(e),
            }
            if verbose:
                print(f"  ✗ Error: {e}")

        results.append(example_result)

    # Calculate summary statistics
    summary = {
        "total_examples": len(dataset),
        "successful_runs": len([r for r in results if r["error"] is None]),
        "failed_runs": len([r for r in results if r["error"] is not None]),
        "metrics": {},
    }

    for key, scores in all_scores.items():
        summary["metrics"][key] = {
            "mean": sum(scores) / len(scores) if scores else None,
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "count": len(scores),
        }

    return {
        "timestamp": datetime.now().isoformat(),
        "dataset": dataset_path,
        "results": results,
        "summary": summary,
    }


def print_summary(eval_output: dict) -> None:
    """Print a formatted summary of evaluation results."""
    summary = eval_output["summary"]

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Dataset: {eval_output['dataset']}")
    print(f"Timestamp: {eval_output['timestamp']}")
    print(f"Total examples: {summary['total_examples']}")
    print(f"Successful: {summary['successful_runs']}")
    print(f"Failed: {summary['failed_runs']}")

    print("\nMetrics:")
    for key, stats in summary["metrics"].items():
        if stats["mean"] is not None:
            print(f"  {key}:")
            print(f"    mean: {stats['mean']:.3f}")
            print(f"    range: [{stats['min']:.3f}, {stats['max']:.3f}]")
            print(f"    count: {stats['count']}")


def main():
    parser = argparse.ArgumentParser(description="Run LegacyLens RAG evaluations")
    parser.add_argument(
        "--dataset",
        type=str,
        default="evals/golden_dataset.json",
        help="Path to dataset JSON file",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        help="Specific example IDs to evaluate",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for JSON results",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    # Run evaluation
    results = run_evaluation(
        dataset_path=args.dataset,
        example_ids=args.ids,
        verbose=not args.quiet,
    )

    # Print summary
    print_summary(results)

    # Save to file if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()

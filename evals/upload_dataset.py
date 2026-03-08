#!/usr/bin/env python
"""Upload golden/labeled datasets to LangSmith.

Usage:
    uv run python evals/upload_dataset.py --file evals/golden_dataset.json --name legacylens-golden
"""

import argparse
import json
from dotenv import load_dotenv
load_dotenv()

from langsmith import Client


def upload_dataset(
    file_path: str,
    dataset_name: str,
    description: str = "",
) -> None:
    """Upload a local JSON dataset to LangSmith.

    Args:
        file_path: Path to local JSON dataset
        dataset_name: Name for the LangSmith dataset
        description: Optional description
    """
    client = Client()

    # Load local dataset
    with open(file_path) as f:
        examples = json.load(f)

    print(f"Loaded {len(examples)} examples from {file_path}")

    # Check if dataset exists
    try:
        existing = client.read_dataset(dataset_name=dataset_name)
        print(f"Dataset '{dataset_name}' already exists (ID: {existing.id})")
        print("Deleting and recreating...")
        client.delete_dataset(dataset_name=dataset_name)
    except Exception:
        pass  # Dataset doesn't exist, that's fine

    # Create dataset
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description=description or f"LegacyLens RAG evaluation dataset from {file_path}",
    )
    print(f"Created dataset: {dataset_name} (ID: {dataset.id})")

    # Add examples
    for ex in examples:
        # Inputs are what gets passed to the target function
        inputs = {"question": ex["question"]}

        # Outputs are reference/expected outputs (optional)
        outputs = {}
        if "expected_answer_contains" in ex:
            outputs["expected_keywords"] = ex["expected_answer_contains"]

        # Metadata contains ground truth labels for evaluators
        metadata = {
            "id": ex["id"],
            "category": ex.get("category"),
            "difficulty": ex.get("difficulty"),
            "expected_answer_contains": ex.get("expected_answer_contains", []),
            "expected_unit_mentioned": ex.get("expected_unit_mentioned"),
            "expected_mentions_call_graph": ex.get("expected_mentions_call_graph", False),
        }

        # Add labels if present (for labeled dataset)
        if "labels" in ex:
            metadata["labels"] = ex["labels"]

        client.create_example(
            inputs=inputs,
            outputs=outputs if outputs else None,
            metadata=metadata,
            dataset_id=dataset.id,
        )

    print(f"Uploaded {len(examples)} examples to LangSmith")
    print(f"View at: https://smith.langchain.com/datasets")


def main():
    parser = argparse.ArgumentParser(description="Upload dataset to LangSmith")
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to local JSON dataset",
    )
    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="LangSmith dataset name",
    )
    parser.add_argument(
        "--description",
        type=str,
        default="",
        help="Dataset description",
    )

    args = parser.parse_args()

    upload_dataset(
        file_path=args.file,
        dataset_name=args.name,
        description=args.description,
    )


if __name__ == "__main__":
    main()

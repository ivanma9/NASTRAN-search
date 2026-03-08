# LegacyLens Evaluation Suite

Evaluators for assessing LLM output quality on the LegacyLens RAG system.

## Datasets

### Golden Dataset (`golden_dataset.json`)
Q&A pairs with expected answer keywords for quality assessment:
- `expected_answer_contains`: Keywords that should appear in the answer
- `expected_unit_mentioned`: Specific subroutine/function name to mention
- `category`: Query type (unit_explanation, dependency_analysis, etc.)
- `difficulty`: easy/medium/hard

### Labeled Dataset (`labeled_dataset.json`)
Questions with metadata labels for classification analysis:
- `query_type`: Type of query being asked
- `requires_*`: Boolean flags for required retrieval capabilities
- `expected_complexity`: simple/moderate/complex
- `domain`: Subject area (matrix_operations, io_operations, etc.)

## Evaluators

| Evaluator | Description | Score Range |
|-----------|-------------|-------------|
| `keyword_coverage` | Fraction of expected keywords found | 0.0 - 1.0 |
| `unit_mention_check` | Whether expected unit name appears | 0 or 1 |
| `answer_length_check` | Word count within acceptable range | 0 or 1 |
| `code_reference_check` | Contains file paths or line numbers | 0 or 1 |
| `fortran_syntax_check` | Uses FORTRAN-specific terminology | 0.0 - 1.0 |
| `call_graph_context_check` | Mentions call relationships | 0 or 1 |
| `no_hallucination_check` | No hedging/uncertainty phrases | 0 or 1 |

## Usage

### Local Evaluation (No LangSmith Required)

```bash
# Run against golden dataset
uv run python evals/run_eval.py --dataset evals/golden_dataset.json

# Run specific examples
uv run python evals/run_eval.py --dataset evals/golden_dataset.json --ids golden_001 golden_002

# Save results to JSON
uv run python evals/run_eval.py --dataset evals/golden_dataset.json --output results.json
```

### LangSmith Experiments

First, set your API key:
```bash
export LANGSMITH_API_KEY=your_key_here
```

Upload dataset to LangSmith:
```bash
uv run python evals/upload_dataset.py --file evals/golden_dataset.json --name legacylens-golden
```

Run experiment:
```bash
uv run python evals/run_langsmith_experiment.py --dataset legacylens-golden
```

### Programmatic Usage

```python
from evals.evaluators import evaluate_rag_output, keyword_coverage

# Single evaluator
result = keyword_coverage(
    output="The DECOMP subroutine performs matrix factorization...",
    expected_keywords=["matrix", "decomposition", "factor"]
)
print(f"{result.key}: {result.score} - {result.comment}")

# Full evaluation against golden example
golden = {
    "expected_answer_contains": ["matrix", "decomposition"],
    "expected_unit_mentioned": "DECOMP",
    "category": "unit_explanation"
}
results = evaluate_rag_output(answer, golden)
for r in results:
    print(f"{r.key}: {r.score}")
```

## Adding New Evaluators

1. Add function to `evaluators.py` following the `EvalResult` return pattern
2. Add LangSmith wrapper if needed (for experiment integration)
3. Update `evaluate_rag_output()` composite function
4. Add to `__init__.py` exports

## Metrics Interpretation

- **keyword_coverage >= 0.5**: Answer covers most expected concepts
- **unit_mention = 1**: Correctly references the queried unit
- **fortran_syntax >= 0.4**: Uses appropriate FORTRAN terminology
- **confidence = 1**: Answer is assertive (not hedging)

"""Context assembly for LLM answer generation."""

SYSTEM_PROMPT = """You are a FORTRAN code expert analyzing the NASA NASTRAN-95 codebase.
NASTRAN-95 is a structural analysis program written in fixed-form FORTRAN 77 with over 1 million lines of code.

When answering questions:
- Always cite specific file paths and line numbers from the provided context
- Explain FORTRAN-specific constructs (COMMON blocks, ENTRY statements, fixed-form conventions)
- Note shared state via COMMON blocks when relevant
- Reference the call relationships between subroutines when applicable
- Be precise about what the code does vs. what you're inferring
- If the retrieved code context is not relevant to the question, say so honestly rather than fabricating an answer. Suggest what kind of question would work better."""


def assemble_context(results: list[dict], indices: dict | None = None) -> str:
    """Assemble LLM context from retrieved chunks.

    Args:
        results: List of dicts from retriever (text, metadata, score, index_context)
        indices: Optional dict with 'common_blocks' and 'call_graph' indices

    Returns:
        Formatted context string for LLM prompt
    """
    parts = [SYSTEM_PROMPT, "\n--- Retrieved Code Context ---\n"]

    for i, result in enumerate(results, 1):
        meta = result["metadata"]
        header = (
            f"\n### Chunk {i}: {meta.get('unit_type', '').upper()} {meta.get('unit_name', 'UNKNOWN')}\n"
            f"File: {meta.get('file_path', 'unknown')}\n"
            f"Lines: {meta.get('line_start', '?')}-{meta.get('line_end', '?')}\n"
        )

        # Metadata annotations
        annotations = []
        common_blocks = meta.get("common_blocks", [])
        if common_blocks and isinstance(common_blocks, list) and common_blocks:
            annotations.append(f"COMMON blocks: {', '.join(common_blocks)}")
        calls = meta.get("calls", [])
        if calls and isinstance(calls, list) and calls:
            annotations.append(f"Calls: {', '.join(calls)}")
        entry_points = meta.get("entry_points", [])
        if entry_points and isinstance(entry_points, list) and entry_points:
            annotations.append(f"Entry points: {', '.join(entry_points)}")

        if annotations:
            header += "Metadata: " + " | ".join(annotations) + "\n"

        # Index context
        index_ctx = result.get("index_context", "").strip()
        if index_ctx:
            header += f"Cross-references: {index_ctx}\n"

        parts.append(header)
        parts.append(f"```fortran\n{result['text']}\n```\n")

    return "\n".join(parts)

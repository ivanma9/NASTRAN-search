"""Context assembly for LLM answer generation."""

from legacylens.config import get_settings

SYSTEM_PROMPT = """You analyze NASA NASTRAN-95 (FORTRAN 77). Be concise. Cite file:line references. If context is irrelevant, say so."""


def assemble_context(results: list[dict], indices: dict | None = None) -> str:
    """Assemble LLM context from retrieved chunks.

    Args:
        results: List of dicts from retriever (text, metadata, score, index_context)
        indices: Optional dict with 'common_blocks' and 'call_graph' indices

    Returns:
        Formatted context string for LLM prompt
    """
    settings = get_settings()
    max_context_chars = settings.max_context_chars
    max_chunk_lines = settings.max_chunk_lines
    parts = [SYSTEM_PROMPT, "\n--- Retrieved Code Context ---\n"]
    char_count = len(SYSTEM_PROMPT) + 40

    for i, result in enumerate(results, 1):
        if char_count > max_context_chars:
            break
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
        # Truncate very long chunks to reduce prompt tokens and LLM latency
        text = result['text']
        lines = text.split('\n')
        if len(lines) > max_chunk_lines:
            text = '\n'.join(lines[:max_chunk_lines]) + '\n... (truncated)'
        chunk_str = f"```fortran\n{text}\n```\n"
        parts.append(chunk_str)
        char_count += len(header) + len(chunk_str)

    return "\n".join(parts)

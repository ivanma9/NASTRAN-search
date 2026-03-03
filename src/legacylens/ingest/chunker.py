"""Regex-based FORTRAN chunker.

Splits preprocessed FORTRAN source at SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA
boundaries. Handles oversized chunks by splitting at labeled sections.
"""

import re
from dataclasses import dataclass, field

import tiktoken

# Patterns for program unit boundaries
UNIT_START_RE = re.compile(
    r"^\s*(SUBROUTINE|FUNCTION|PROGRAM|BLOCK\s*DATA)\s+(\w+)",
    re.IGNORECASE,
)
# Also match typed functions like "INTEGER FUNCTION FOO"
TYPED_FUNC_RE = re.compile(
    r"^\s*(?:INTEGER|REAL|DOUBLE\s*PRECISION|COMPLEX|LOGICAL|CHARACTER)\s+FUNCTION\s+(\w+)",
    re.IGNORECASE,
)
UNIT_END_RE = re.compile(r"^\s*END\s*$", re.IGNORECASE)

DEFAULT_MAX_TOKENS = 1500


@dataclass
class FortranChunk:
    text: str
    file_path: str
    line_start: int
    line_end: int
    unit_name: str = ""
    unit_type: str = ""
    common_blocks: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    externals: list[str] = field(default_factory=list)
    comment_ratio: float = 0.0
    token_count: int = 0


def _count_tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Fallback: rough estimate
        return len(text) // 4


def _parse_unit_header(line: str) -> tuple[str, str] | None:
    """Extract (unit_type, unit_name) from a line, or None."""
    # Check typed function first
    m = TYPED_FUNC_RE.match(line)
    if m:
        return ("function", m.group(1).upper())

    m = UNIT_START_RE.match(line)
    if m:
        unit_type = m.group(1).upper().replace(" ", "_")
        if unit_type == "BLOCK_DATA":
            unit_type = "block_data"
        else:
            unit_type = unit_type.lower()
        unit_name = m.group(2).upper()
        return (unit_type, unit_name)

    return None


def _split_oversized(chunk: FortranChunk, max_tokens: int) -> list[FortranChunk]:
    """Split an oversized chunk at comment block boundaries."""
    lines = chunk.text.splitlines()
    if len(lines) <= 2:
        return [chunk]

    # Find the signature line (first non-comment, non-empty line)
    signature = ""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("C") and not stripped.startswith("*"):
            signature = line
            break

    sub_chunks = []
    current_lines: list[str] = []
    current_start = chunk.line_start
    line_offset = 0

    for i, line in enumerate(lines):
        current_lines.append(line)
        # Check if we've hit the token limit
        current_text = "\n".join(current_lines)
        if _count_tokens(current_text) > max_tokens and len(current_lines) > 10:
            # Split here — create a sub-chunk from accumulated lines (minus last)
            split_lines = current_lines[:-1]
            sub_text = "\n".join(split_lines)
            if sub_chunks:  # Prepend signature to continuation chunks
                sub_text = signature + "\nC     ... (continued)\n" + sub_text

            sub_chunks.append(FortranChunk(
                text=sub_text,
                file_path=chunk.file_path,
                line_start=current_start,
                line_end=current_start + len(split_lines) - 1,
                unit_name=chunk.unit_name,
                unit_type=chunk.unit_type,
            ))
            current_start = chunk.line_start + i
            current_lines = [line]

    # Remaining lines
    if current_lines:
        sub_text = "\n".join(current_lines)
        if sub_chunks:
            sub_text = signature + "\nC     ... (continued)\n" + sub_text
        sub_chunks.append(FortranChunk(
            text=sub_text,
            file_path=chunk.file_path,
            line_start=current_start,
            line_end=chunk.line_end,
            unit_name=chunk.unit_name,
            unit_type=chunk.unit_type,
        ))

    return sub_chunks if sub_chunks else [chunk]


def chunk_fortran(
    text: str,
    file_path: str,
    line_map: dict[int, int],
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[FortranChunk]:
    """Split preprocessed FORTRAN text into chunks at program unit boundaries.

    Args:
        text: Preprocessed (uppercased, continuations joined) FORTRAN source
        file_path: Path to the source file
        line_map: Mapping from preprocessed line index to original line number
        max_tokens: Maximum tokens per chunk before splitting

    Returns:
        List of FortranChunk objects
    """
    lines = text.splitlines()
    chunks: list[FortranChunk] = []

    current_lines: list[str] = []
    current_unit_name = ""
    current_unit_type = ""
    current_start_idx = 0

    def _flush():
        nonlocal current_lines, current_unit_name, current_unit_type, current_start_idx
        if not current_lines:
            return
        # Skip chunks that are all empty/whitespace
        if not any(line.strip() for line in current_lines):
            current_lines = []
            return

        chunk_text = "\n".join(current_lines)
        start_line = line_map.get(current_start_idx, current_start_idx + 1)
        end_idx = current_start_idx + len(current_lines) - 1
        end_line = line_map.get(end_idx, end_idx + 1)

        chunk = FortranChunk(
            text=chunk_text,
            file_path=file_path,
            line_start=start_line,
            line_end=end_line,
            unit_name=current_unit_name,
            unit_type=current_unit_type,
        )

        # Handle oversized chunks
        if _count_tokens(chunk_text) > max_tokens:
            chunks.extend(_split_oversized(chunk, max_tokens))
        else:
            chunks.append(chunk)

        current_lines = []
        current_unit_name = ""
        current_unit_type = ""

    for i, line in enumerate(lines):
        header = _parse_unit_header(line)
        if header:
            # Flush any accumulated lines before this unit
            _flush()
            current_unit_type, current_unit_name = header
            current_start_idx = i
            current_lines = [line]
        elif UNIT_END_RE.match(line):
            current_lines.append(line)
            _flush()
            current_start_idx = i + 1
        else:
            if not current_lines and not current_unit_name:
                current_start_idx = i
            current_lines.append(line)

    # Flush remaining
    _flush()

    # Compute token counts
    for chunk in chunks:
        chunk.token_count = _count_tokens(chunk.text)

    return chunks

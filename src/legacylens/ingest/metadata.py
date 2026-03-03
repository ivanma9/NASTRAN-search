"""Metadata extraction from FORTRAN chunks.

Extracts COMMON blocks, CALL statements, ENTRY points, INCLUDE directives,
EXTERNAL declarations, and computes comment ratio.
"""

import re

from legacylens.ingest.chunker import FortranChunk, _count_tokens

COMMON_RE = re.compile(r"COMMON\s*/\s*(\w+)\s*/", re.IGNORECASE)
CALL_RE = re.compile(r"CALL\s+(\w+)", re.IGNORECASE)
ENTRY_RE = re.compile(r"^\s*ENTRY\s+(\w+)", re.IGNORECASE | re.MULTILINE)
INCLUDE_RE = re.compile(r"INCLUDE\s+['\"]([^'\"]+)['\"]", re.IGNORECASE)
EXTERNAL_RE = re.compile(r"EXTERNAL\s+(.+)", re.IGNORECASE)


def extract_metadata(chunk: FortranChunk) -> FortranChunk:
    """Extract metadata from a FortranChunk's text and update in place."""
    text = chunk.text

    # COMMON blocks
    chunk.common_blocks = sorted(set(
        f"/{m.upper()}/" for m in COMMON_RE.findall(text)
    ))

    # CALL statements
    chunk.calls = sorted(set(
        m.upper() for m in CALL_RE.findall(text)
    ))

    # ENTRY points
    chunk.entry_points = sorted(set(
        m.upper() for m in ENTRY_RE.findall(text)
    ))

    # INCLUDE directives
    chunk.includes = sorted(set(INCLUDE_RE.findall(text)))

    # EXTERNAL declarations
    externals = set()
    for match in EXTERNAL_RE.findall(text):
        # EXTERNAL can list multiple names separated by commas
        for name in match.split(","):
            name = name.strip().upper()
            if name:
                externals.add(name)
    chunk.externals = sorted(externals)

    # Comment ratio
    lines = text.splitlines()
    total = len(lines)
    if total > 0:
        comment_count = sum(
            1 for line in lines
            if line.strip() and len(line) > 0 and line[0] in ("C", "*", "!")
        )
        chunk.comment_ratio = round(comment_count / total, 3)

    # Token count
    chunk.token_count = _count_tokens(text)

    return chunk

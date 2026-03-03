"""COMMON block cross-reference index.

Maps COMMON block names to all subroutines/functions that reference them,
enabling dependency queries like "What subroutines share state through /SYSTEM/?".
"""

import json
import logging
from pathlib import Path

from legacylens.ingest.chunker import FortranChunk

logger = logging.getLogger(__name__)

INDEX_PATH = Path("data/indices/common_blocks.json")


def build_common_block_index(chunks: list[FortranChunk]) -> dict:
    """Build a COMMON block cross-reference index from chunks.

    Returns:
        dict mapping block names to their references:
        {"/SYSTEM/": {"referenced_by": [{"file": ..., "unit": ..., "line": ...}]}}
    """
    index: dict[str, dict] = {}

    for chunk in chunks:
        for block_name in chunk.common_blocks:
            if block_name not in index:
                index[block_name] = {"referenced_by": []}

            index[block_name]["referenced_by"].append({
                "file": chunk.file_path,
                "unit": chunk.unit_name,
                "line": chunk.line_start,
            })

    # Sort references by unit name for consistency
    for block_name in index:
        index[block_name]["referenced_by"].sort(key=lambda r: r["unit"])

    logger.info(f"Built COMMON block index: {len(index)} blocks")
    return index


def save_index(index: dict, path: Path | None = None) -> None:
    """Save the COMMON block index to a JSON file."""
    out = path or INDEX_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=2))
    logger.info(f"Saved COMMON block index to {out}")


def load_index(path: Path | None = None) -> dict:
    """Load the COMMON block index from a JSON file."""
    src = path or INDEX_PATH
    if not src.exists():
        return {}
    return json.loads(src.read_text())


def lookup_common_block(name: str, index: dict | None = None) -> list[dict]:
    """Look up which subroutines reference a given COMMON block."""
    if index is None:
        index = load_index()

    # Normalize: ensure /NAME/ format
    if not name.startswith("/"):
        name = f"/{name}/"
    name = name.upper()

    entry = index.get(name, {})
    return entry.get("referenced_by", [])


def find_shared_state(unit_name: str, chunks: list[FortranChunk] | None = None, index: dict | None = None) -> list[str]:
    """Find what COMMON blocks a given program unit uses."""
    if chunks:
        for chunk in chunks:
            if chunk.unit_name.upper() == unit_name.upper():
                return chunk.common_blocks
    if index is None:
        index = load_index()
    blocks = []
    for block_name, data in index.items():
        for ref in data.get("referenced_by", []):
            if ref["unit"].upper() == unit_name.upper():
                blocks.append(block_name)
                break
    return sorted(blocks)

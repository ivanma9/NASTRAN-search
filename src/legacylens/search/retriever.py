"""Vector search + index-augmented retrieval."""

import json
import logging
import re

import chromadb
import voyageai

from legacylens.config import get_settings
from legacylens.index.call_graph import load_index as load_call_graph
from legacylens.index.common_blocks import load_index as load_common_index
from legacylens.index.common_blocks import lookup_common_block

logger = logging.getLogger(__name__)

# --- Cached singletons (avoid re-init on every request) ---
_voyage_client = None
_chroma_collection = None
_cached_common_index = None
_cached_call_graph = None


def _get_voyage_client():
    global _voyage_client
    if _voyage_client is None:
        settings = get_settings()
        _voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
    return _voyage_client


def _get_chroma_collection():
    global _chroma_collection
    if _chroma_collection is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chromadb_path)
        _chroma_collection = client.get_collection(name=settings.collection_name)
    return _chroma_collection


def _get_indices():
    global _cached_common_index, _cached_call_graph
    if _cached_common_index is None:
        _cached_common_index = load_common_index()
    if _cached_call_graph is None:
        _cached_call_graph = load_call_graph()
    return _cached_common_index, _cached_call_graph


# Pattern to detect COMMON block or subroutine names in queries
COMMON_BLOCK_RE = re.compile(r"(?:COMMON\s+(?:block\s+)?)?/(\w+)/", re.IGNORECASE)
# Forward: "subroutine DECOMP" — keyword before name (highest priority)
_UNIT_FWD_RE = re.compile(
    r"\b(?:subroutine|function|program|module)\s+(\w+)\b", re.IGNORECASE
)
# Reverse: "DECOMP subroutine" — name before keyword
_UNIT_REV_RE = re.compile(
    r"\b(\w+)\s+(?:subroutine|function|program|module)\b", re.IGNORECASE
)
# Standalone uppercase names (e.g. DECOMP, XREAD) — used as fallback for call graph
UNIT_NAME_RE = re.compile(r"\b([A-Z][A-Z0-9]{2,})\b")

# Keep a combined regex for backward compatibility in tests
SUBROUTINE_RE = _UNIT_FWD_RE


def _extract_unit_name(query: str) -> str | None:
    """Extract a unit name from a natural language query.

    Collects candidates from forward and reverse patterns, then picks the best
    one (preferring uppercase FORTRAN-style identifiers over common English words).
    """
    candidates = []

    # Collect from forward: "subroutine DECOMP"
    for m in _UNIT_FWD_RE.finditer(query):
        candidates.append(m.group(1))

    # Collect from reverse: "DECOMP subroutine"
    for m in _UNIT_REV_RE.finditer(query):
        candidates.append(m.group(1))

    if not candidates:
        return None

    # Prefer uppercase names (FORTRAN identifiers) over common English words
    upper_candidates = [c for c in candidates if c.isupper() and len(c) >= 3]
    if upper_candidates:
        return upper_candidates[0].upper()

    # Fall back to first candidate
    return candidates[0].upper()

# ChromaDB returns cosine distance (0 = identical, 2 = opposite).
# Discard results with distance above this threshold (low relevance).
MAX_DISTANCE_THRESHOLD = 1.2


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Retrieve relevant chunks for a query.

    Uses vector similarity search augmented with index lookups when the query
    mentions specific COMMON blocks or subroutine names.
    Filters out results below a minimum relevance threshold.

    Returns:
        List of dicts with keys: text, metadata, score, index_context
    """
    settings = get_settings()
    k = top_k or settings.top_k

    # Embed query (cached client)
    client = _get_voyage_client()
    response = client.embed([query], model=settings.embedding_model, input_type="query")
    query_embedding = response.embeddings[0]

    # ChromaDB search (cached collection)
    # Overfetch to give re-ranking and injection more candidates to work with
    collection = _get_chroma_collection()
    fetch_k = k + 5

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=fetch_k,
    )

    # Build result list
    retrieved = []
    for i in range(len(results["ids"][0])):
        metadata = results["metadatas"][0][i]
        # Decode JSON-encoded list fields
        for field in ("common_blocks", "calls", "entry_points", "includes", "externals"):
            if field in metadata and isinstance(metadata[field], str):
                try:
                    metadata[field] = json.loads(metadata[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        retrieved.append({
            "text": results["documents"][0][i],
            "metadata": metadata,
            "score": results["distances"][0][i] if results["distances"] else 0,
            "index_context": "",
        })

    # Filter out low-relevance results
    retrieved = [r for r in retrieved if r["score"] <= MAX_DISTANCE_THRESHOLD]

    # Deduplicate sub-chunks: keep only best score per unit_name
    _deduplicate_by_unit(retrieved)

    # Keyword re-ranking: boost results that contain query-relevant terms
    _keyword_rerank(query, retrieved)

    # Index-augmented retrieval (includes direct chunk injection)
    _augment_with_indices(query, retrieved, collection)

    # Trim back to requested top_k after re-ranking and injection
    return retrieved[:k]


def _deduplicate_by_unit(results: list[dict]) -> None:
    """Keep only the lowest-distance chunk per unit_name.

    Chunks with empty or missing unit_name are always kept.
    Modifies the list in place.
    """
    seen: dict[str, int] = {}  # unit_name -> index of best result
    to_remove: list[int] = []

    for i, r in enumerate(results):
        unit = r["metadata"].get("unit_name", "")
        if not unit:
            continue
        if unit in seen:
            prev_idx = seen[unit]
            if r["score"] < results[prev_idx]["score"]:
                to_remove.append(prev_idx)
                seen[unit] = i
            else:
                to_remove.append(i)
        else:
            seen[unit] = i

    for idx in sorted(to_remove, reverse=True):
        results.pop(idx)


# Keywords that signal specific coding concepts in Fortran queries
_IO_KEYWORDS = re.compile(
    r"\b(READ|WRITE|OPEN|CLOSE|REWIND|BACKSPACE|ENDFILE|INQUIRE|FORMAT|"
    r"FILE|I/?O|INPUT|OUTPUT|PRINT|PUNCH|TAPE|UNIT)\b",
    re.IGNORECASE,
)
_ERROR_KEYWORDS = re.compile(
    r"\b(ERROR|FATAL|DIAG|MESAGE|ABORT|WARNING|FAIL)\b",
    re.IGNORECASE,
)
_MATRIX_KEYWORDS = re.compile(
    r"\b(DECOMP|SOLVE|MATRIX|INVERT|EIGEN|FACTOR|PIVOT|DIAGONAL|FBS|"
    r"BANDWIDTH|SPARSE|SYMMETRIC|TRIANGUL)\b",
    re.IGNORECASE,
)
_ELEMENT_KEYWORDS = re.compile(
    r"\b(ELEMENT|STIFFNESS|MASS|LOAD|FORCE|STRESS|STRAIN|DOF|ASSEMBLE|"
    r"RIGID|CONSTRAINT|PLATE|BAR|BEAM|QUAD|TRIA)\b",
    re.IGNORECASE,
)
_DATA_MGMT_KEYWORDS = re.compile(
    r"\b(GINO|TABLE|BUFFER|SCRATCH|POOL|FIST|MCB|TRAILER|PURGE|EQUIV)\b",
    re.IGNORECASE,
)
_KEYWORD_PATTERNS = [
    _IO_KEYWORDS, _ERROR_KEYWORDS, _MATRIX_KEYWORDS,
    _ELEMENT_KEYWORDS, _DATA_MGMT_KEYWORDS,
]

# Bonus per keyword match (subtracted from distance; lower = better)
_KEYWORD_BONUS = 0.08
_MAX_KEYWORD_BONUS = 0.35


def _keyword_rerank(query: str, results: list[dict]) -> None:
    """Apply keyword-based re-ranking bonus to results.

    For conceptual queries (I/O, error handling), results containing relevant
    keywords get a distance bonus, then results are re-sorted.
    """
    # Collect keywords present in the query
    query_keywords: list[re.Pattern] = []
    for pattern in _KEYWORD_PATTERNS:
        if pattern.search(query):
            query_keywords.append(pattern)

    if not query_keywords:
        return

    for r in results:
        text = r["text"].upper()
        match_count = 0
        for pattern in query_keywords:
            match_count += len(pattern.findall(text))
        bonus = min(match_count * _KEYWORD_BONUS, _MAX_KEYWORD_BONUS)
        r["score"] = max(r["score"] - bonus, 0.0)

    results.sort(key=lambda r: r["score"])


def _augment_with_indices(query: str, results: list[dict], collection=None) -> None:
    """Augment results with cross-reference index data."""
    try:
        common_index = load_common_index()
        call_graph = load_call_graph()
    except Exception:
        return  # Indices not available yet

    if not common_index and not call_graph:
        return

    # Check if query mentions a COMMON block
    common_match = COMMON_BLOCK_RE.search(query)
    if common_match:
        block_name = f"/{common_match.group(1).upper()}/"
        refs = lookup_common_block(block_name, common_index)
        if refs:
            context = f"COMMON block {block_name} is referenced by: "
            context += ", ".join(f"{r['unit']} ({r['file']}:{r['line']})" for r in refs[:5])
            for r in results:
                r["index_context"] += context + "\n"

    # Check if query mentions a subroutine name
    unit_name = _extract_unit_name(query)
    if not unit_name:
        # Fallback: look for standalone uppercase names in the call graph
        for m in UNIT_NAME_RE.finditer(query):
            candidate = m.group(1)
            if call_graph and candidate in call_graph:
                unit_name = candidate
                break

    # Fix 1: Direct chunk injection — if we know the unit name, fetch its chunk
    # directly from ChromaDB and prepend it if not already in results.
    # If the exact unit doesn't exist, try partial matches from the call graph.
    if unit_name and collection is not None:
        existing_units = {r["metadata"].get("unit_name") for r in results}
        inject_targets = [unit_name]

        # If exact unit isn't in call graph, look for partial matches
        if call_graph and unit_name not in call_graph:
            for key in call_graph:
                if unit_name in key and key != unit_name:
                    inject_targets.append(key)
                    if len(inject_targets) >= 3:
                        break

        injected = 0
        for target in inject_targets:
            if target in existing_units:
                continue
            try:
                direct = collection.get(
                    where={"unit_name": target},
                    limit=1,
                    include=["documents", "metadatas"],
                )
                if direct["ids"]:
                    meta = direct["metadatas"][0]
                    for field in ("common_blocks", "calls", "entry_points", "includes", "externals"):
                        if field in meta and isinstance(meta[field], str):
                            try:
                                meta[field] = json.loads(meta[field])
                            except (json.JSONDecodeError, TypeError):
                                pass
                    results.insert(injected, {
                        "text": direct["documents"][0],
                        "metadata": meta,
                        "score": 0.0,
                        "index_context": "",
                    })
                    existing_units.add(target)
                    injected += 1
            except Exception:
                pass

    if unit_name and call_graph:
        entry = call_graph.get(unit_name, {})
        if entry:
            parts = []
            if entry.get("calls"):
                parts.append(f"{unit_name} calls: {', '.join(entry['calls'][:5])}")
            if entry.get("called_by"):
                parts.append(f"{unit_name} is called by: {', '.join(entry['called_by'][:5])}")
            if parts:
                context_str = "\n".join(parts) + "\n"
                # Only append to the result whose unit_name matches the queried unit
                target = None
                for r in results:
                    if r["metadata"].get("unit_name") == unit_name:
                        target = r
                        break
                # Fallback: append to first result so LLM still sees it
                if target is None and results:
                    target = results[0]
                if target is not None:
                    target["index_context"] += context_str

    # Also augment each result with its own COMMON block / call relationships
    for r in results:
        meta = r["metadata"]
        parts = []
        if meta.get("common_blocks") and isinstance(meta["common_blocks"], list):
            for block in meta["common_blocks"]:
                refs = lookup_common_block(block, common_index)
                other_units = [ref["unit"] for ref in refs if ref["unit"] != meta.get("unit_name")]
                if other_units:
                    parts.append(f"Shares COMMON {block} with: {', '.join(other_units[:5])}")
        if meta.get("unit_name") and call_graph:
            entry = call_graph.get(meta["unit_name"], {})
            if entry.get("called_by"):
                parts.append(f"Called by: {', '.join(entry['called_by'][:5])}")
        if parts:
            r["index_context"] += "\n".join(parts)

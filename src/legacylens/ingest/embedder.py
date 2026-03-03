"""Voyage code-3 batch embedding module."""

import logging
import time

import voyageai

from legacylens.config import get_settings
from legacylens.ingest.chunker import FortranChunk

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
# Token-aware batching: stay under TPM limit per batch
MAX_TOKENS_PER_BATCH = 80000  # Voyage max is 120K; use conservative estimate
MAX_CHUNKS_PER_BATCH = 50  # Cap to avoid exceeding per-batch token limit
RPM_SLEEP = 0.5  # seconds between batches


def _estimate_tokens(text: str) -> int:
    # Voyage tokenizer uses more tokens than len/4; use len/3 for safety
    return len(text) // 3


def _build_batches(chunks: list[FortranChunk]) -> list[list[FortranChunk]]:
    """Build token-aware batches that stay under rate limits."""
    batches: list[list[FortranChunk]] = []
    current_batch: list[FortranChunk] = []
    current_tokens = 0

    for chunk in chunks:
        est = _estimate_tokens(chunk.text)
        if current_batch and (current_tokens + est > MAX_TOKENS_PER_BATCH or len(current_batch) >= MAX_CHUNKS_PER_BATCH):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(chunk)
        current_tokens += est

    if current_batch:
        batches.append(current_batch)

    return batches


def embed_chunks(
    chunks: list[FortranChunk],
) -> list[tuple[FortranChunk, list[float]]]:
    """Embed chunks using Voyage code-3 in token-aware batches.

    Respects rate limits (3 RPM, 10K TPM for free tier).
    Returns list of (chunk, embedding_vector) tuples.
    """
    settings = get_settings()
    client = voyageai.Client(api_key=settings.voyage_api_key)

    batches = _build_batches(chunks)
    results: list[tuple[FortranChunk, list[float]]] = []
    total_tokens = 0

    logger.info(f"Embedding {len(chunks)} chunks in {len(batches)} batches")

    for batch_idx, batch in enumerate(batches):
        texts = [c.text for c in batch]

        for attempt in range(MAX_RETRIES):
            try:
                response = client.embed(
                    texts,
                    model=settings.embedding_model,
                    input_type="document",
                )
                for chunk, embedding in zip(batch, response.embeddings):
                    results.append((chunk, embedding))
                total_tokens += response.total_tokens
                if (batch_idx + 1) % 10 == 0 or batch_idx == 0 or batch_idx == len(batches) - 1:
                    logger.info(
                        f"Batch {batch_idx + 1}/{len(batches)} — "
                        f"{len(results)}/{len(chunks)} chunks, {total_tokens:,} tokens"
                    )
                break
            except Exception as e:
                err_str = str(e)
                if "rate" in err_str.lower() or "429" in err_str or "reduced rate" in err_str.lower():
                    wait = RPM_SLEEP * (attempt + 1)
                    logger.warning(f"Rate limited (attempt {attempt + 1}). Waiting {wait}s...")
                    time.sleep(wait)
                elif attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Batch failed (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"Batch failed after {MAX_RETRIES} attempts: {e}. Skipping {len(batch)} chunks.")

        # Sleep to stay under 3 RPM
        if batch_idx < len(batches) - 1:
            time.sleep(RPM_SLEEP)

    logger.info(f"Embedding complete: {len(results)} chunks, {total_tokens:,} total tokens")
    return results

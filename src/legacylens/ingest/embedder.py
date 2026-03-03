"""Voyage code-3 batch embedding module."""

import logging
import time

import voyageai

from legacylens.config import get_settings
from legacylens.ingest.chunker import FortranChunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 128
MAX_RETRIES = 3


def embed_chunks(
    chunks: list[FortranChunk],
) -> list[tuple[FortranChunk, list[float]]]:
    """Embed chunks using Voyage code-3 in batches.

    Returns list of (chunk, embedding_vector) tuples.
    """
    settings = get_settings()
    client = voyageai.Client(api_key=settings.voyage_api_key)

    results: list[tuple[FortranChunk, list[float]]] = []
    total_tokens = 0

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
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
                logger.info(
                    f"Embedded batch {i // BATCH_SIZE + 1} "
                    f"({len(batch)} chunks, {response.total_tokens} tokens)"
                )
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Embedding batch failed (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"Embedding batch failed after {MAX_RETRIES} attempts: {e}. Skipping {len(batch)} chunks.")

    logger.info(f"Embedding complete: {len(results)} chunks, {total_tokens} total tokens")
    return results

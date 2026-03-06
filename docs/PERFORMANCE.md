# LegacyLens Performance Metrics

> Last updated: 2026-03-03

## Performance Targets

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Query latency | <3 seconds end-to-end | ~2.2s avg (local), ~2.9s avg (production) | Met |
| Retrieval precision | >70% relevant chunks in top-5 | 93% (13/14 benchmark queries) | Met |
| Codebase coverage | 100% of files indexed | 1,848 files / 4,520 chunks in ChromaDB | Met |
| Ingestion throughput | 10,000+ LOC in <5 minutes | ~1.8K files ingested with token-aware batching | Met |
| Answer accuracy | Correct file/line references | Enforced via system prompt + metadata (file_path, line_start, line_end) | Met |

## Detailed Metrics

### Query Latency

| Stat | Value |
|------|-------|
| Average | 2.2s (local) / 2.9s (production) |
| p50 | 2.15s |
| p95 | 3.38s |

Measured across 14 benchmark queries spanning 5 query types (specific unit, conceptual, dependency, entry point, irrelevant).

### Retrieval Precision

| Query Type | Hit Rate | Avg Distance |
|------------|----------|--------------|
| Specific unit | 4/4 (100%) | 0.934 |
| Conceptual | 4/5 (80%) | 0.676 |
| Dependency | 3/3 (100%) | 0.918 |
| Entry point | 1/1 (100%) | 0.944 |
| Irrelevant | 1/1 (100%) | 1.262 |
| **Overall** | **13/14 (93%)** | **0.863** |

Distance is cosine distance (0 = identical, 2 = opposite). Results above 1.2 are filtered as low-relevance.

### Codebase Coverage

| Stat | Value |
|------|-------|
| Source files indexed | 1,848 Fortran files (.f, .for, .ftn) |
| Total chunks | 4,520 |
| Unique unit names | 1,856 |
| ChromaDB size | ~84 MB |

### Ingestion Throughput

| Setting | Value |
|---------|-------|
| Embedding model | voyage-code-3 (1536-dim) |
| Max tokens/batch | 80,000 |
| Max chunks/batch | 50 |
| Rate limit sleep | 0.5s between batches |
| Resumable | Yes (skips existing chunk IDs) |

### Answer Accuracy

| Setting | Value |
|---------|-------|
| LLM model | gpt-4o-mini |
| Temperature | 0.1 |
| Max tokens | 120 |
| Citation format | file:line enforced via system prompt |
| Context cap | 3,000 chars, chunks truncated to 25 lines |

## Optimization History

| Date | Change | Impact |
|------|--------|--------|
| 2026-03-03 | Streaming responses + max_tokens 2000→800 | Perceived latency improvement |
| 2026-03-03 | Client caching, LRU cache, context caps, max_tokens→120, top_k 5→3 | 9.6s → 2.9s avg (70% reduction) |
| 2026-03-03 | Keyword re-ranking, direct chunk injection, overfetch+trim | 2.9s → 2.2s avg, accuracy 79% → 93% |

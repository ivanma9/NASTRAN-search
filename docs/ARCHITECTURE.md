# LegacyLens — Architecture & System Design

**Date:** 2026-03-02

---

## RAG Architecture Documentation

### Vector DB Selection

**Choice: ChromaDB (embedded)**

ChromaDB was selected for its zero-infrastructure footprint — it runs in-process with no separate server, making it ideal for a single-user CLI tool shipped alongside a pre-built index. The embedded mode persists vectors to disk (`data/chromadb/`, ~84 MB for NASTRAN-95) and loads into memory on first query.

**Tradeoffs considered:**

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **ChromaDB** | Zero setup, Python-native, persistent, free | No hybrid search, limited filtering expressivity | ✅ Chosen for MVP |
| Qdrant | Hybrid search, disk-backed at 100M+ vectors, server mode | Requires Docker/process management | Upgrade path |
| FAISS | Extremely fast ANN search | No metadata filtering, no persistence layer | Rejected (no metadata) |
| pgvector | SQL + vectors in one system | Requires PostgreSQL | Rejected (too heavy) |

ChromaDB's cosine distance metric is a natural fit: FORTRAN subroutines with similar functionality (e.g., matrix decomposition routines) cluster tightly regardless of naming conventions.

---

### Embedding Strategy

**Model: `voyage-code-3` (Voyage AI), 1536 dimensions**

Voyage code-3 was chosen over general-purpose embeddings (OpenAI `text-embedding-3-small`, `ada-002`) because it is explicitly trained on source code. For FORTRAN 77, this matters: the model understands token patterns like `COMMON /BLOCK/`, `CALL SUBNAME`, and fixed-form column layout that general embeddings treat as noise.

**Why it fits code understanding:**
- Trained on multi-language code corpora, including legacy languages
- 1536-dim vectors provide fine-grained discrimination between structurally similar but functionally different subroutines (e.g., `DCOMP` vs `DECOMP`)
- Separate `input_type` for `"document"` (ingestion) vs `"query"` (retrieval) aligns embedding space for asymmetric search
- Empirically: average cosine distance of 0.863 across benchmark queries, with irrelevant queries scoring ~1.262 (above the 1.2 filter threshold)

---

### Chunking Approach

**Strategy: Program-unit boundary detection via regex**

FORTRAN 77 has a well-defined program unit structure — every callable unit begins with `SUBROUTINE`, `FUNCTION`, `PROGRAM`, or `BLOCK DATA` and ends with a bare `END` statement. The chunker exploits this to create semantically complete chunks.

**Process:**
1. **Preprocessing** (`preprocess.py`): Join continuation lines (column 6 non-blank), normalize case to uppercase, track original→preprocessed line mapping
2. **Boundary detection** (`chunker.py`): Regex scan for `SUBROUTINE name`, `FUNCTION name`, typed functions (`INTEGER FUNCTION name`), and `END` statements
3. **Oversized splitting**: Chunks exceeding 1,500 tokens are split at comment block boundaries; continuation chunks prepend the unit signature for context
4. **Filtering**: Discard chunks with <10 characters, <5 tokens, or all-comment content

**Result:** 4,520 chunks from 1,848 files, 1,856 unique unit names. Average chunk size ~300 tokens, well within Voyage's embedding window.

**Key design decision:** Chunking at program-unit boundaries (not fixed line windows) ensures each chunk is a complete, callable unit — meaning retrieved chunks can be directly read and cited by the LLM without dangling context.

---

### Retrieval Pipeline

**5-stage pipeline: embed → search → filter → re-rank → augment**

```
Query
  │
  ├─ 1. Embed query (Voyage code-3, input_type="query")
  │
  ├─ 2. ChromaDB cosine search (overfetch: top_k + 5 candidates)
  │
  ├─ 3. Distance filter (discard score > 1.2) + deduplication (best chunk per unit_name)
  │
  ├─ 4. Keyword re-ranking: detect domain keywords (I/O, error, matrix, element, data mgmt)
  │      → apply -0.08 distance bonus per keyword match (max -0.35), re-sort
  │
  ├─ 5. Index augmentation:
  │      a. COMMON block lookup: query mentions /BLOCK/ → annotate with referencing units
  │      b. Unit name extraction: forward/reverse patterns + uppercase fallback
  │      c. Direct chunk injection: named unit not in results → fetch by metadata
  │      d. Call graph enrichment: X calls [...], X is called by [...]
  │      e. Per-result cross-references: shared COMMON blocks, caller lists
  │
  └─ Trim to top_k → context assembly → GPT-4o-mini generation
```

**Context assembly** caps at 3,000 characters total, with each chunk truncated to 25 lines. System prompt instructs the LLM to cite `file:line` references. LLM uses temperature 0.1 and max 120 tokens for fast, precise answers.

---

### Failure Modes

**Known limitations and edge cases discovered:**

| Failure Mode | Description | Mitigation |
|---|---|---|
| **Conceptual queries miss** | "How does NASTRAN handle singularities?" retrieves weakly related chunks | Keyword re-ranking partially helps; fundamentally limited by 3 retrieved chunks |
| **Unnamed code blocks** | File-level code between program units gets no `unit_name`, poor retrievability | Stored but rarely surface in results |
| **Ambiguous unit names** | `DCOMP` vs `DECOMP` vs `CDCOMP` — partial match injection can return wrong unit | Partial match limited to 3 candidates; exact match prioritized |
| **Fixed-form artifacts** | Column 1-6 label fields and sequence numbers create token noise in embeddings | Preprocessing strips sequence numbers but labels remain |
| **Irrelevant question handling** | Queries unrelated to NASTRAN return results with distance ~1.2–1.4 | Distance threshold at 1.2 filters most; LLM still sees 0–3 chunks |
| **LRU cache staleness** | Non-streaming `/api/ask` caches 128 queries in-process; restart clears cache | Acceptable for single-session use |
| **Short answers** | max_tokens=120 truncates multi-step explanations | Trade-off for latency; users can re-ask for elaboration |

---

### Performance Results

**Measured across 14 benchmark queries, 5 query types:**

| Metric | Result |
|--------|--------|
| Average latency (local) | 2.2s end-to-end |
| Average latency (production) | 2.9s end-to-end |
| p50 latency | 2.15s |
| p95 latency | 3.38s |
| Overall retrieval precision | **93%** (13/14 benchmark queries) |
| Codebase coverage | 1,848 files / 4,520 chunks / 1,856 units |
| ChromaDB index size | ~84 MB |

**Precision by query type:**

| Query Type | Hit Rate | Avg Distance |
|---|---|---|
| Specific unit (e.g., "explain DCOMP") | 4/4 (100%) | 0.934 |
| Conceptual (e.g., "I/O handling") | 4/5 (80%) | 0.676 |
| Dependency (e.g., "what calls XREAD") | 3/3 (100%) | 0.918 |
| Entry point lookup | 1/1 (100%) | 0.944 |
| Irrelevant (out-of-domain) | 1/1 (100%) filtered | 1.262 |

**Optimization history:**

| Change | Impact |
|--------|--------|
| Streaming + max_tokens 2000→800 | Improved perceived latency |
| LRU cache + context caps + top_k 5→3 | 9.6s → 2.9s avg (70% reduction) |
| Keyword re-ranking + direct chunk injection + overfetch | 2.9s → 2.2s avg, precision 79% → 93% |

**Example: query "What does subroutine DCOMP do?"**
- Retrieval: DCOMP chunk injected directly (score 0.0), augmented with call graph (calls XREAD, DECOMP; called by SOLVER)
- Latency: 1.8s
- Answer: Correctly identifies DCOMP as the matrix decomposition entry point, cites `nastran95/dcomp.f:1`

---


## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        User Interface                         │
│                                                              │
│   CLI (Typer + Rich)              Web API (FastAPI)          │
│   legacylens ingest <path>        POST /query                │
│   legacylens ask "question"       GET /health                │
└──────────┬───────────────────────────────┬───────────────────┘
           │                               │
     ┌─────▼─────┐                   ┌─────▼─────┐
     │  Ingest   │                   │  Search   │
     │  Service  │                   │  Service  │
     └─────┬─────┘                   └─────┬─────┘
           │                               │
     ┌─────▼───────────────────────────────▼─────┐
     │              Data Layer                    │
     │                                            │
     │  ChromaDB (MVP) / Qdrant (production)      │
     │  Vectors + Metadata + COMMON block index   │
     └─────┬───────────────────────────────┬─────┘
           │                               │
     ┌─────▼─────┐                   ┌─────▼─────┐
     │ Voyage    │                   │ GPT-4o-   │
     │ code-3    │                   │ mini      │
     │ (embed)   │                   │ (generate)│
     └───────────┘                   └───────────┘
```

## Project Structure

```
legacylens/
├── pyproject.toml               # Project config, dependencies, CLI entry point
├── .env                         # API keys (VOYAGE_API_KEY, OPENAI_API_KEY)
├── .env.example                 # Template without secrets
├── README.md
│
├── src/
│   └── legacylens/
│       ├── __init__.py
│       ├── config.py            # Settings: API keys, paths, model config, chunk sizes
│       │
│       ├── cli.py               # Typer app — top-level commands
│       │   # Commands:
│       │   #   legacylens ingest <path> [--subset <dir>]
│       │   #   legacylens ask "question" [--model sonnet] [--top-k 5]
│       │   #   legacylens stats          (index statistics)
│       │   #   legacylens validate       (spot-check chunks)
│       │
│       ├── ingest/              # Phase A: Ingestion Pipeline
│       │   ├── __init__.py
│       │   ├── discovery.py     # Find FORTRAN source files by extension
│       │   ├── preprocess.py    # Fixed-form preprocessing
│       │   ├── chunker.py       # Regex-based FORTRAN chunker
│       │   ├── metadata.py      # Extract metadata from chunk text
│       │   ├── embedder.py      # Voyage code-3 batch embedding
│       │   ├── storage.py       # ChromaDB write operations
│       │   └── pipeline.py      # Orchestrate full ingestion flow
│       │
│       ├── search/              # Phase B: Search & Answer Pipeline
│       │   ├── __init__.py
│       │   ├── retriever.py     # Vector similarity search
│       │   ├── context.py       # Assemble context from retrieved chunks
│       │   ├── generator.py     # LLM answer generation
│       │   └── pipeline.py      # Orchestrate full query flow
│       │
│       ├── index/               # Cross-reference indices (post-MVP)
│       │   ├── __init__.py
│       │   ├── common_blocks.py # COMMON block cross-reference map
│       │   └── call_graph.py    # Call graph from CALL metadata
│       │
│       ├── features/            # Code understanding features (post-MVP)
│       │   ├── __init__.py
│       │   ├── explain.py       # Code explanation
│       │   ├── dependencies.py  # Dependency mapping
│       │   ├── patterns.py      # Pattern detection
│       │   └── docgen.py        # Documentation generation
│       │
│       └── api/                 # Web API (post-MVP)
│           ├── __init__.py
│           ├── app.py           # FastAPI app
│           └── routes.py        # /query, /health endpoints
│
├── data/
│   ├── chromadb/                # Persistent vector store (gitignored, or shipped pre-built)
│   └── indices/                 # COMMON block index, call graph (JSON)
│
├── tests/
│   ├── unit/
│   │   ├── test_chunker.py      # Chunk boundary detection
│   │   ├── test_preprocess.py   # Continuation line joining, case normalization
│   │   ├── test_metadata.py     # Metadata extraction accuracy
│   │   ├── test_discovery.py    # File extension filtering
│   │   └── test_retriever.py    # Search result formatting
│   ├── integration/
│   │   ├── test_ingest.py       # End-to-end: files → ChromaDB
│   │   └── test_query.py        # End-to-end: question → answer
│   └── eval/
│       ├── dataset.json         # 50+ test cases (query, expected tool calls, expected output)
│       └── run_evals.py         # LangSmith eval runner
│
└── docs/
    ├── pre-search-legacylens.md # Pre-search research document
    ├── PRD.md                   # Full product requirements
    ├── PRD-MVP.md               # MVP-scoped requirements
    ├── ARCHITECTURE.md          # This file
    └── COST_ANALYSIS.md         # AI cost tracking + projections
```

## Data Flow

### Phase A: Ingestion Pipeline (run once)

```
NASTRAN-95 source directory (1,848 files)
        │
        ▼
┌─────────────────┐
│  discovery.py   │  Glob for .f, .for, .ftn files
│                 │  Output: sorted list of absolute file paths
└────────┬────────┘
         ▼
┌─────────────────┐
│ preprocess.py   │  Per file:
│                 │  1. Detect fixed-form (columns 1-6 special)
│                 │  2. Join continuation lines (col 6 non-blank)
│                 │  3. Normalize case to uppercase
│                 │  4. Track original→preprocessed line mapping
│                 │  Output: cleaned text + line_map dict
└────────┬────────┘
         ▼
┌─────────────────┐
│  chunker.py     │  Split at program unit boundaries:
│                 │  - SUBROUTINE name ... END
│                 │  - FUNCTION name ... END (incl. typed: INTEGER FUNCTION)
│                 │  - PROGRAM name ... END
│                 │  - BLOCK DATA name ... END
│                 │  Handle oversized chunks (>1500 tokens):
│                 │    split at comment block boundaries, prepend signature
│                 │  Filter: remove <10 chars, <5 tokens, comment-only
│                 │  Token counting: tiktoken cl100k_base (fallback: len/4)
│                 │  Output: list of FortranChunk objects
└────────┬────────┘
         ▼
┌─────────────────┐
│  metadata.py    │  Per chunk, extract via regex:
│                 │  - unit_name, unit_type
│                 │  - common_blocks: COMMON /NAME/ → ["/NAME/"]
│                 │  - calls: CALL SUBNAME → ["SUBNAME"]
│                 │  - entry_points: ENTRY NAME → ["NAME"]
│                 │  - includes: INCLUDE 'file' → ["file"]
│                 │  - externals: EXTERNAL A,B → ["A","B"]
│                 │  - comment_ratio: fraction of comment lines
│                 │  Output: enriched FortranChunk with metadata dict
└────────┬────────┘
         ▼
┌─────────────────┐
│  embedder.py    │  Batch embed via Voyage code-3 API (1536-dim)
│                 │  - Token-aware batching: 50 chunks / 80K tokens per batch
│                 │  - Rate limiting: 0.5s sleep between batches (3 RPM)
│                 │  - Retry: exponential backoff, max 5 retries
│                 │  - input_type: "document"
│                 │  Output: list of (chunk, embedding_vector) pairs
└────────┬────────┘
         ▼
┌─────────────────┐
│  storage.py     │  Write to ChromaDB:
│                 │  - Collection: "nastran95"
│                 │  - Document: chunk text
│                 │  - Embedding: Voyage vector
│                 │  - Metadata: all fields (lists JSON-encoded)
│                 │  - ID: "{file_path}:{line_start}"
│                 │  - Batch size: 500 per ChromaDB upsert
│                 │  - Resumable: skips existing chunk IDs
│                 │  Persist to data/chromadb/
└────────┬────────┘
         ▼
┌─────────────────┐
│  Index build    │  Post-storage index construction:
│                 │  - call_graph.py: bidirectional call graph
│                 │    {unit: {calls: [...], called_by: [...]}}
│                 │  - common_blocks.py: COMMON block cross-references
│                 │    {"/BLOCK/": {referenced_by: [{unit, file, line}]}}
│                 │  Saved to data/indices/*.json
└────────┬────────┘
         ▼
    ChromaDB (4,520 chunks, 1,856 units, ~84MB)
    + call_graph.json + common_blocks.json
```

### Phase B: Retrieval Pipeline (run many times)

```
User question (natural language)
        │
        ├──── POST /api/ask (cached) ──── LRU cache (128 slots)
        │                                  ↓ cache miss
        ├──── POST /api/ask/stream (SSE) ─┐
        │                                  │
        ▼                                  ▼
┌──────────────────────────────────────────────────┐
│ retriever.py — retrieve(query, top_k)            │
│                                                  │
│  1. Embed query via Voyage code-3                │
│     - input_type: "query"                        │
│     - Singleton cached client                    │
│                                                  │
│  2. ChromaDB cosine similarity search            │
│     - Overfetch: top_k + 5 candidates            │
│     - Default top_k: 3                           │
│     - Decode JSON-encoded metadata fields        │
│                                                  │
│  3. Keyword re-ranking (_keyword_rerank)         │
│     - Detect I/O keywords: READ, WRITE, OPEN,   │
│       CLOSE, FILE, PRINT, TAPE, UNIT, etc.      │
│     - Detect error keywords: ERROR, FATAL,       │
│       ABORT, WARNING, DIAG, etc.                 │
│     - Bonus: -0.08 per match (max -0.35)         │
│     - Re-sort by adjusted score                  │
│                                                  │
│  4. Index augmentation (_augment_with_indices)   │
│     a. COMMON block lookup:                      │
│        Query mentions /BLOCK/ → annotate results │
│        with "referenced by: UNIT1, UNIT2..."     │
│     b. Unit name extraction:                     │
│        Forward: "subroutine DECOMP"              │
│        Reverse: "DECOMP subroutine"              │
│        Fallback: standalone uppercase (call graph)│
│     c. Direct chunk injection:                   │
│        Named unit not in results → fetch from    │
│        ChromaDB by metadata, prepend (score 0.0) │
│        Partial match: DCOMP → DDCOMP, CDCOMP     │
│     d. Call graph enrichment:                    │
│        "X calls: [...]", "X is called by: [...]" │
│     e. Per-result cross-references:              │
│        Shared COMMON blocks, caller lists        │
│                                                  │
│  5. Trim results back to top_k                   │
│                                                  │
│  Output: [{text, metadata, score, index_context}]│
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│ context.py — assemble_context(results)           │
│                                                  │
│  Per chunk (up to 3000 chars total):             │
│  - Header: "### Chunk i: SUBROUTINE FOO"         │
│  - Location: "File: path, Lines: start-end"      │
│  - Metadata: COMMON blocks, calls, entry points  │
│  - Cross-references from index_context           │
│  - Code: truncated to 25 lines max               │
│  System prompt: "You analyze NASA NASTRAN-95      │
│    (FORTRAN 77). Be concise. Cite file:line."    │
│                                                  │
│  Output: formatted markdown context string       │
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│ generator.py — generate_answer / _stream         │
│                                                  │
│  LLM: gpt-4o-mini (singleton cached client)      │
│  - System message: assembled context             │
│  - User message: original question               │
│  - temperature: 0.1                              │
│  - max_tokens: 120                               │
│                                                  │
│  Non-streaming: returns full answer string       │
│  Streaming: yields tokens via generator          │
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│ api.py — Response to client                      │
│                                                  │
│  /api/ask (non-streaming):                       │
│    → QueryResponse {answer, chunks[]}            │
│    → LRU cached (128 entries, instant on repeat) │
│                                                  │
│  /api/ask/stream (SSE):                          │
│    → event: chunks  (full chunk metadata JSON)   │
│    → event: token   (individual tokens {t: "x"}) │
│    → event: done                                 │
│                                                  │
│  ChunkResponse: {file_path, line_start, line_end,│
│    unit_name, unit_type, text, score}            │
└──────────────────────────────────────────────────┘
```

### Key Configuration Values

| Setting | Value | Module | Effect |
|---------|-------|--------|--------|
| `embedding_model` | `voyage-code-3` | embedder, retriever | 1536-dim code embeddings |
| `llm_model` | `gpt-4o-mini` | generator | Answer generation |
| `chunk_max_tokens` | 1500 | chunker | Max tokens per ingested chunk |
| `top_k` | 3 | retriever | Default results returned |
| `max_tokens` (LLM) | 120 | generator | Max answer length |
| `temperature` | 0.1 | generator | Low randomness for accuracy |
| `MAX_CONTEXT_CHARS` | 3000 | context | Total prompt context cap |
| `MAX_TOKENS_PER_BATCH` | 80,000 | embedder | Voyage API batch limit |
| `MAX_CHUNKS_PER_BATCH` | 50 | embedder | Chunks per API call |
| `RPM_SLEEP` | 0.5s | embedder | Rate limit between batches |
| `LRU cache size` | 128 | api | Cached query results |
| `MAX_DISTANCE_THRESHOLD` | 1.2 | retriever | Discard low-relevance results |
| Overfetch | `k + 5` | retriever | Extra candidates for re-ranking |
| Keyword bonus | -0.08/match | retriever | Re-ranking boost per keyword |
| Max keyword bonus | -0.35 | retriever | Cap on re-ranking adjustment |

## Data Models

### FortranChunk

```python
@dataclass
class FortranChunk:
    text: str                    # The actual code text
    file_path: str               # Absolute path to source file
    line_start: int              # First line in original file
    line_end: int                # Last line in original file
    unit_name: str               # e.g., "DCOMP", "XREAD"
    unit_type: str               # "subroutine" | "function" | "program" | "block_data"
    common_blocks: list[str]     # e.g., ["/SYSTEM/", "/XDATA/"]
    calls: list[str]             # e.g., ["DCOMP", "XREAD", "WRITE"]
    entry_points: list[str]      # e.g., ["DCOMP2"] for ENTRY statements
    includes: list[str]          # e.g., ["common.inc"]
    externals: list[str]         # e.g., ["DABS", "DSQRT"]
    comment_ratio: float         # 0.0 - 1.0
    token_count: int             # Approximate token count for embedding budget
```

### ChromaDB Schema

```
Collection: "nastran95"
├── id: str                     # "{file_path}:{line_start}"
├── document: str               # Chunk text
├── embedding: list[float]      # Voyage code-3 vector (1536 dims)
└── metadata: dict
    ├── unit_name: str
    ├── unit_type: str
    ├── file_path: str
    ├── line_start: int
    ├── line_end: int
    ├── common_blocks: str      # JSON-encoded list (ChromaDB metadata is flat)
    ├── calls: str              # JSON-encoded list
    ├── entry_points: str       # JSON-encoded list
    ├── includes: str           # JSON-encoded list
    ├── comment_ratio: float
    └── token_count: int
```

### COMMON Block Index (post-MVP)

```
data/indices/common_blocks.json

{
  "/SYSTEM/": {
    "variables": ["NSYS", "NBUF", "NOUT"],
    "referenced_by": [
      {"file": "src/dcomp.f", "unit": "DCOMP", "line": 45},
      {"file": "src/xread.f", "unit": "XREAD", "line": 12}
    ]
  },
  ...
}
```

### Call Graph (post-MVP)

```
data/indices/call_graph.json

{
  "DCOMP": {
    "calls": ["XREAD", "WRITE", "DABS"],
    "called_by": ["MAIN", "SOLVER"],
    "file": "src/dcomp.f",
    "line": 1
  },
  ...
}
```

## API Design (post-MVP)

### POST /query

```json
// Request
{
  "question": "What subroutines reference COMMON block /SYSTEM/?",
  "top_k": 5,
  "model": "gpt-4o-mini"
}

// Response
{
  "answer": "The COMMON block /SYSTEM/ is referenced by 3 subroutines...",
  "sources": [
    {
      "file_path": "src/dcomp.f",
      "line_start": 1,
      "line_end": 87,
      "unit_name": "DCOMP",
      "code_snippet": "      SUBROUTINE DCOMP\nC     ...",
      "relevance_score": 0.92
    }
  ],
  "model": "gpt-4o-mini",
  "tokens_used": { "input": 2340, "output": 456 },
  "latency_ms": 1820
}
```

### GET /health

```json
{
  "status": "ok",
  "index_loaded": true,
  "chunk_count": 4521,
  "codebase": "NASTRAN-95"
}
```

## External Dependencies

| Dependency | Purpose | Auth |
|-----------|---------|------|
| Voyage AI API | Embedding generation | `VOYAGE_API_KEY` |
| OpenAI API | Answer generation (GPT-4o-mini) | `OPENAI_API_KEY` |
| Anthropic API (optional) | Answer generation (Claude Sonnet) | `ANTHROPIC_API_KEY` |
| LangSmith (optional) | Tracing + evals | `LANGSMITH_API_KEY` |

All API keys stored in `.env`, loaded via `pydantic-settings` or `python-dotenv`.

## Error Handling

**Ingestion errors:**
- If a file fails to parse, log the error and continue with remaining files
- Print a summary of skipped files at the end
- Exit code 0 if any files succeeded, non-zero if all failed
- Support resumable ingestion: skip already-stored chunks on re-run (check by chunk ID `file_path:line_start`)

**Embedding API failures:**
- Retry with exponential backoff (3 attempts)
- If a batch fails after retries, skip those chunks and log them for manual review

**Query failures:**
- If embedding or LLM API is unavailable, print a clear error message with the service name
- Suggest checking API keys / network connectivity

## Index Size

Estimated ChromaDB index size for NASTRAN-95 (~1M LOC): **~200-500MB** (vectors + metadata). This is feasible for:
- Git LFS as a release artifact
- Direct inclusion in the project (users skip ingestion)
- Re-generation via `legacylens ingest` if not shipped

## Scaling Considerations

**Current design (single-user CLI):** ChromaDB embedded, all in-process, no server.

**If scaling to multi-user web service:**

| Concern | Current | Upgrade Path |
|---------|---------|-------------|
| Vector DB | ChromaDB (embedded) | Qdrant (server mode) — adds hybrid search, better filtering |
| Concurrency | Single process | FastAPI + async handlers |
| Index size | ~1M LOC in RAM | Qdrant handles 100M+ vectors with disk-backed storage |
| Query caching | None | Redis or in-memory LRU for repeated queries |
| Rate limiting | None | FastAPI middleware |
| Cost control | Pay-per-query | Query budget per user, model tiering |

## Build & Run

```bash
# Setup
git clone <repo>
cd legacylens
cp .env.example .env  # Add API keys
uv sync

# Ingest (run once)
uv run legacylens ingest ./NASTRAN-95/

# Query
uv run legacylens ask "Where is the main entry point?"
uv run legacylens ask "What subroutines reference COMMON block /SYSTEM/?"
uv run legacylens ask "Explain what DCOMP does" --model sonnet

# Stats
uv run legacylens stats

# Tests
uv run pytest tests/unit/ -v
uv run python tests/eval/run_evals.py
```

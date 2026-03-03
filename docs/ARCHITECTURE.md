# LegacyLens — Architecture & System Design

**Date:** 2026-03-02

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

### Phase A: Ingestion (run once)

```
NASTRAN-95 source directory
        │
        ▼
┌─────────────────┐
│  discovery.py   │  Glob for .f, .for, .ftn files
│  → file list    │  Output: list of absolute file paths
└────────┬────────┘
         ▼
┌─────────────────┐
│ preprocess.py   │  Per file:
│                 │  1. Read raw text
│                 │  2. Detect fixed-form (columns 1-6 special)
│                 │  3. Join continuation lines (col 6 non-blank)
│                 │  4. Track original line number mapping
│                 │  Output: cleaned text + line number map
└────────┬────────┘
         ▼
┌─────────────────┐
│  chunker.py     │  Split at program unit boundaries:
│                 │  - SUBROUTINE name ... END
│                 │  - FUNCTION name ... END
│                 │  - PROGRAM name ... END
│                 │  - BLOCK DATA name ... END
│                 │  Handle oversized chunks (>1500 tokens):
│                 │    split at labeled sections, prepend signature
│                 │  Output: list of FortranChunk objects
└────────┬────────┘
         ▼
┌─────────────────┐
│  metadata.py    │  Per chunk, extract via regex:
│                 │  - unit_name, unit_type
│                 │  - common_blocks: COMMON /NAME/
│                 │  - calls: CALL SUBNAME
│                 │  - entry_points: ENTRY NAME
│                 │  - includes: INCLUDE 'file'
│                 │  - externals: EXTERNAL names
│                 │  - file_path, line_start, line_end
│                 │  - comment_ratio
│                 │  Output: enriched FortranChunk with metadata dict
└────────┬────────┘
         ▼
┌─────────────────┐
│  embedder.py    │  Batch embed all chunks via Voyage code-3 API
│                 │  - Batch size: 128 chunks per API call
│                 │  - Retry with exponential backoff
│                 │  - Track total tokens + cost
│                 │  Output: list of (chunk, embedding vector) pairs
└────────┬────────┘
         ▼
┌─────────────────┐
│  storage.py     │  Write to ChromaDB:
│                 │  - Collection: "nastran95"
│                 │  - Document: chunk text
│                 │  - Embedding: voyage vector
│                 │  - Metadata: all extracted fields
│                 │  - ID: file_path:line_start
│                 │  Persist to data/chromadb/
└────────┬────────┘
         ▼
    Static index
    (portable artifact)
```

### Phase B: Search & Answer (run many times)

```
User question (natural language)
        │
        ▼
┌─────────────────┐
│ retriever.py    │  1. Embed query via Voyage code-3
│                 │  2. ChromaDB similarity search (top-k=5)
│                 │  3. Optional: metadata filter (unit_type, common_blocks)
│                 │  Output: list of (chunk, metadata, score) tuples
└────────┬────────┘
         ▼
┌─────────────────┐
│  context.py     │  Assemble LLM context:
│                 │  1. Format each chunk with file path + line range header
│                 │  2. Include metadata (COMMON blocks, calls) as annotations
│                 │  3. Add surrounding code context (±N lines) if available
│                 │  4. Prepend system prompt with instructions
│                 │  Output: formatted prompt string
└────────┬────────┘
         ▼
┌─────────────────┐
│ generator.py    │  Call LLM (GPT-4o-mini default):
│                 │  - System: "You are a FORTRAN code expert..."
│                 │  - Context: assembled chunks with metadata
│                 │  - Question: user's query
│                 │  - Instruction: include file/line refs in answer
│                 │  Output: answer string with citations
└────────┬────────┘
         ▼
┌─────────────────┐
│   cli.py        │  Render with Rich:
│                 │  - Answer text (markdown)
│                 │  - Code blocks (syntax highlighted)
│                 │  - File references (clickable paths)
│                 │  - Relevance scores
└─────────────────┘
```

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

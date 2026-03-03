# LegacyLens — MVP Product Requirements Document

**Date:** 2026-03-02
**Deadline:** 24 hours (Day 1)
**Scope:** Minimum viable RAG pipeline for NASTRAN-95

---

## Goal

A working end-to-end pipeline: ingest NASTRAN-95 FORTRAN source → build searchable vector index → answer natural language questions about the code via CLI. All 6 reference test queries from the spec must return relevant results with correct file/line references.

## What Ships

### 1. Ingestion CLI (`legacylens ingest <path>`)

Batch-process NASTRAN-95 source files into a searchable ChromaDB index.

**Input:** Path to NASTRAN-95 source directory
**Output:** Persistent ChromaDB directory + ingestion summary

| Step | What It Does | Implementation |
|------|-------------|----------------|
| File discovery | Recursively find `.f`, `.for`, `.ftn` files | `pathlib.glob` |
| Preprocessing | Join continuation lines (column 6), normalize case, track line numbers | Custom Python — ~50 lines |
| Chunking | Split at SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA boundaries | Regex: `^\s*(SUBROUTINE\|FUNCTION\|PROGRAM\|BLOCK\s*DATA)\s+(\w+)` / `^\s*END\s*$` |
| Metadata extraction | Per chunk: unit_name, unit_type, file_path, line_start, line_end, common_blocks, calls | Regex patterns on chunk text |
| Embedding | Generate vectors for all chunks | Voyage code-3 API (batch) |
| Storage | Store vectors + metadata | ChromaDB (embedded, persistent directory) |
| Validation | Print summary: files, chunks, tokens, cost | Counts + spot-check |

**Scoping decision:** If NASTRAN-95 is too large for Day 1, scope to one subsystem directory. Expand to full codebase on Day 2 after pipeline is validated.

### 2. Query CLI (`legacylens ask "..."`)

Natural language questions answered from the pre-built index.

**Input:** Natural language question string
**Output:** Answer with code snippets, file paths, and line numbers

| Step | What It Does | Implementation |
|------|-------------|----------------|
| Query embedding | Embed the question | Voyage code-3 API |
| Vector search | Find top-5 similar chunks | ChromaDB similarity search |
| Context assembly | Combine chunks with file/line metadata | String formatting |
| Answer generation | LLM synthesizes answer from context | GPT-4o-mini (OpenAI API) |
| Display | Syntax-highlighted code + file references | Typer + Rich |

### 3. Test Queries (6 from spec)

These must return relevant, accurate results:

1. "Where is the main entry point of this program?"
2. "What functions modify the CUSTOMER-RECORD?" (adapted: "What subroutines reference COMMON block /SYSTEM/?")
3. "Explain what the CALCULATE-INTEREST paragraph does" (adapted: "Explain what subroutine DCOMP does")
4. "Find all file I/O operations"
5. "What are the dependencies of MODULE-X?" (adapted: "What does subroutine XREAD call?")
6. "Show me error handling patterns in this codebase"

## What Does NOT Ship in MVP

- Hybrid search (BM25 + vector) — vector-only is sufficient for Day 1
- Re-ranking
- Web API / deployment
- Code understanding features beyond basic Q&A
- COMMON block cross-reference index
- Eval suite (just the 6 manual test queries)
- Multi-model support (`--model` flag)
- Conversation history

## Technical Decisions (Locked for MVP)

| Decision | Choice | Why |
|----------|--------|-----|
| Vector DB | ChromaDB (embedded) | `pip install`, zero config, persistent to disk |
| Embedding | Voyage code-3 | Best code retrieval quality. One-time cost for static codebase. |
| LLM | GPT-4o-mini | Cheapest. Sufficient for synthesizing from retrieved context. |
| Chunking | Regex splitter | NASTRAN-95 is fixed-form F77. Regex handles SUBROUTINE/END reliably. |
| CLI | Typer + Rich | Fast to build. Syntax highlighting. |
| Framework | LlamaIndex | Ingestion pipeline primitives. ChromaDB integration. |

## File Structure (MVP)

```
legacylens/
├── pyproject.toml
├── .env                     # VOYAGE_API_KEY, OPENAI_API_KEY
├── src/
│   └── legacylens/
│       ├── __init__.py
│       ├── cli.py           # Typer app: ingest + ask commands
│       ├── ingest/
│       │   ├── __init__.py
│       │   ├── discovery.py # Find FORTRAN files
│       │   ├── preprocess.py# Fixed-form preprocessing
│       │   ├── chunker.py   # Regex-based FORTRAN chunker
│       │   ├── metadata.py  # Extract metadata from chunks
│       │   └── pipeline.py  # Orchestrate: discover → preprocess → chunk → embed → store
│       ├── search/
│       │   ├── __init__.py
│       │   ├── retriever.py # ChromaDB vector search
│       │   ├── context.py   # Assemble context from chunks
│       │   └── generator.py # LLM answer generation
│       └── config.py        # Settings, API keys, paths
├── data/
│   └── chromadb/            # Persistent vector store (created by ingest)
└── tests/
    └── unit/
        ├── test_chunker.py  # Verify chunks have correct boundaries
        ├── test_metadata.py # Verify extracted metadata
        └── test_preprocess.py # Verify continuation line joining
```

## Acceptance Criteria

- [ ] `legacylens ingest ./NASTRAN-95/` completes without errors
- [ ] Ingestion summary shows: file count, chunk count, total tokens, embedding cost
- [ ] `legacylens ask "Where is the main entry point?"` returns a relevant answer with file path and line numbers
- [ ] All 6 test queries return relevant code snippets
- [ ] File/line references in answers map to actual source code
- [ ] Chunks preserve complete subroutines (no mid-function splits)
- [ ] Metadata includes unit_name, file_path, line_start, line_end for every chunk
- [ ] Total embedding cost for full ingestion is <$5

## Build Order

```
1. Config + .env loading                          (15 min)
2. File discovery (find all .f files)             (15 min)
3. Fixed-form preprocessor (continuation lines)   (30 min)
4. Regex chunker (SUBROUTINE/END boundaries)      (45 min)
5. Metadata extractor (name, COMMON, CALL)        (30 min)
6. Unit tests for chunker + preprocessor          (30 min)
7. Embedding + ChromaDB storage pipeline          (45 min)
8. Run ingestion on NASTRAN-95 subset             (15 min)
9. Validate chunks (spot-check 10 chunks)         (15 min)
── Phase A complete ──
10. Query embedding + ChromaDB retrieval          (30 min)
11. Context assembly                              (20 min)
12. LLM answer generation (GPT-4o-mini)           (30 min)
13. CLI output with Rich syntax highlighting      (30 min)
14. Test all 6 queries                            (30 min)
15. Fix chunking/retrieval issues found           (60 min)
── Phase B complete, MVP done ──
```

**Total estimated: ~7 hours of focused work.**

# LegacyLens — Product Requirements Document

**Date:** 2026-03-02
**Status:** Draft
**Target Codebase:** NASA NASTRAN-95 (github.com/nasa/NASTRAN-95)

---

## 1. Overview

LegacyLens is a RAG-powered system that makes large legacy FORTRAN codebases queryable and understandable through natural language. It ingests a static codebase once, builds a searchable vector index with rich metadata, and lets developers ask questions about code they've never seen before.

**Primary interface:** CLI tool
**Target codebase:** NASA NASTRAN-95 — 1,000,000+ lines of fixed-form FORTRAN (structural analysis, 1970s era)

## 2. Problem

Legacy codebases in FORTRAN, COBOL, and similar languages power critical infrastructure but are increasingly difficult to maintain. The engineers who wrote them are retiring, documentation is sparse, and existing AI code tools (Copilot, Cody, Cursor) don't handle legacy languages well. Embedding models are trained on modern languages. AST parsers have immature legacy grammars. No tool adequately handles FORTRAN-specific constructs like COMMON blocks, fixed-form formatting, or GOTO-based control flow.

## 3. Users

| User | Need |
|------|------|
| New developer onboarding to legacy project | "Where is the main entry point?" / "What does this subroutine do?" |
| Maintenance engineer | "What functions modify COMMON block X?" / "Show me all I/O operations" |
| Modernization team | "What calls this function?" / "What would break if I change this?" |
| Code auditor | "Find error handling patterns" / "Show me all external dependencies" |

## 4. Two-Phase Architecture

NASTRAN-95 is a static codebase (no active development). This enables a clean decoupled architecture:

**Phase A — Ingest (run once):** Batch process the entire codebase → chunk → embed → store. One-time cost. The resulting index is a static, portable artifact.

**Phase B — Search & Answer (run many times):** Query the pre-built index. Read-only. Fast, cheap, repeatable.

## 5. Selected Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python | Richest RAG ecosystem. All SDKs are Python-first. |
| RAG Framework | LlamaIndex | Purpose-built for RAG. Best ingestion pipeline abstractions. |
| Vector DB | ChromaDB (MVP) → Qdrant (prod) | Embedded/zero-config for CLI. Qdrant upgrade for hybrid search. |
| Embeddings | Voyage code-3 | 13-17% better than alternatives on code retrieval benchmarks. |
| LLM | GPT-4o-mini (default) / Claude Sonnet (optional) | 20x cheaper default. Sonnet available via `--model sonnet`. |
| Chunking | Regex-based FORTRAN splitter | Fixed-form F77 needs regex, not tree-sitter (free-form only). |
| CLI | Typer + Rich | Syntax highlighting, fast to build. |
| Observability | LangSmith | Free tier. Built-in eval framework. |
| Hosting | Render (free tier) | Zero-cost public deployment for submission requirement. |
| Testing | Pytest + LangSmith evals | Unit tests for correctness. Evals for RAG quality. |

## 6. Features — Full Scope

### 6.1 Ingestion Pipeline (Phase A)

**P0 — Must have:**
- File discovery: recursively scan for `.f`, `.for`, `.ftn` files
- Fixed-form preprocessing: join continuation lines, normalize case, preserve line numbers
- Regex-based chunking at SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA boundaries
- Metadata extraction per chunk: unit name, unit type, file path, line range, COMMON blocks, CALL list, ENTRY points, INCLUDE directives
- Embedding generation via Voyage code-3 (batch)
- ChromaDB storage with metadata
- Ingestion summary: files processed, chunks created, tokens embedded, cost
- Validation pass: verify chunk count, metadata completeness

**P1 — Should have:**
- COMMON block cross-reference index (block name → subroutines that reference it)
- Oversized chunk splitting at labeled sections with context prepending
- Call graph construction from extracted CALL metadata
- Comment ratio tracking per chunk

**P2 — Nice to have:**
- INCLUDE file expansion (inline included code before chunking)
- EQUIVALENCE statement tracking
- Statement label / GOTO flow analysis
- Pre-built index shipped with project (users skip ingestion)

### 6.2 Query Pipeline (Phase B)

**P0 — Must have:**
- Natural language query input via CLI (`legacylens ask "..."`)
- Query embedding via Voyage code-3
- Vector similarity search (top-k chunks from ChromaDB)
- Context assembly: combine retrieved chunks with surrounding code (±N lines)
- LLM answer generation with file/line references
- Syntax-highlighted code output in terminal (Rich)
- Confidence/relevance scores per retrieved chunk

**P1 — Should have:**
- Hybrid search (BM25 + vector) via Qdrant upgrade
- Re-ranking retrieved results before LLM synthesis
- `--model` flag to switch between GPT-4o-mini and Claude Sonnet
- Drill-down: ability to view full file context around a result
- Conversation history (multi-turn queries)

**P2 — Nice to have:**
- Streaming LLM responses
- Query suggestions based on codebase structure
- Export results to markdown

### 6.3 Code Understanding Features

Implement at least 4 of these (spec requirement):

| Feature | Description | Priority |
|---------|-------------|----------|
| Code Explanation | Explain what a subroutine/function does in plain English | P0 |
| Dependency Mapping | Show what calls what, COMMON block data flow | P0 |
| Pattern Detection | Find similar code patterns across the codebase | P1 |
| Documentation Generation | Generate documentation for undocumented subroutines | P1 |
| Impact Analysis | What would be affected if this code changes? | P1 |
| Translation Hints | Suggest modern Fortran or C equivalents | P2 |
| Bug Pattern Search | Find potential issues based on known anti-patterns | P2 |
| Business Logic Extraction | Identify and explain computational rules in code | P2 |

### 6.4 Web API

**P1 — Should have (spec requires "deployed and publicly accessible"):**
- FastAPI web API on Render (free tier)
- POST `/query` endpoint accepting natural language questions
- JSON response with answer, code snippets, file references, confidence
- GET `/health` endpoint
- Pre-built index loaded at startup (no ingestion needed on server)

### 6.5 Evaluation

**P0 — Must have:**
- 6 reference test queries from spec working correctly
- 5+ unit test cases for chunking and metadata extraction

**P1 — Should have:**
- 50+ test cases in LangSmith dataset
- Retrieval precision@5 measurement (target: >70%)
- Answer faithfulness scoring
- File/line reference accuracy validation

**P2 — Nice to have:**
- Automated eval run in CI
- Regression detection across chunking strategy changes
- Adversarial test cases (ambiguous queries, out-of-scope questions)

### 6.6 Documentation & Deliverables

| Deliverable | Description |
|-------------|-------------|
| Pre-Search Document | This document (completed) |
| RAG Architecture Doc | System design, chunking strategy, retrieval pipeline |
| AI Cost Analysis | Dev spend + projections for 100/1K/10K/100K users |
| Eval Dataset | 50+ test cases with results |
| Demo Video (3-5 min) | Show queries, retrieval results, answer generation |
| GitHub Repository | Setup guide, architecture overview, deployed link |
| Deployed Application | Public URL on Render |

## 7. Performance Targets

| Metric | Target |
|--------|--------|
| Query latency | <3 seconds end-to-end |
| Retrieval precision | >70% relevant chunks in top-5 |
| Codebase coverage | 100% of files indexed |
| Ingestion throughput | 10,000+ LOC in <5 minutes |
| Answer accuracy | Correct file/line references |

## 8. Non-Goals

- Real-time codebase monitoring or incremental re-indexing (codebase is static)
- Multi-language support beyond FORTRAN (this version targets NASTRAN-95 only)
- Code modification or refactoring tools (read-only analysis)
- Production multi-user deployment (single-user CLI tool)
- GUI-first interface (CLI-first, web API is for submission requirement only)

## 9. Timeline

| Day | Focus |
|-----|-------|
| Day 1 | MVP: Ingest NASTRAN-95, basic search + answer, 6 test queries |
| Day 2 | Improve chunking quality, add code understanding features |
| Day 3 | Eval suite (50+ cases), measure precision, hybrid search if needed |
| Day 4-5 | Deploy to Render, polish CLI, documentation, cost analysis |

## 10. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Embeddings weak on FORTRAN | Medium-High | Hybrid search (BM25 + vector) in Qdrant upgrade |
| NASTRAN-95 too large for MVP | Medium | Scope to one subsystem directory first |
| Regex chunker misses edge cases | Medium | Validation pass after ingestion. Manual spot-checks. |
| Incorrect file/line references | Medium | Store absolute line numbers in metadata. Verify at retrieval. |
| Voyage API rate limits during ingest | Low | Batch calls. Retry with backoff. |

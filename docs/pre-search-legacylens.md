# LegacyLens — Pre-Search Document

**Date:** 2026-03-02
**Project:** LegacyLens — RAG system for understanding legacy codebases
**Target Codebase:** NASA NASTRAN-95 (github.com/nasa/NASTRAN-95)
**Status:** Pre-implementation research

---

## Scope of This Document

This is a **pre-search research document** — it evaluates the problem space, surveys alternatives for every technology decision, and records rationale. It is NOT a technical specification. Implementation details (API contracts, database schemas, error codes, deployment configs) live in the companion documents:
- **PRD.md** — Full product requirements with prioritized features
- **PRD-MVP.md** — MVP-scoped requirements (24-hour deadline)
- **ARCHITECTURE.md** — System design, data models, API schemas, file structure

### Goals
- Make legacy FORTRAN codebases queryable via natural language
- Provide accurate file/line references in all answers
- Support the full NASTRAN-95 codebase (1M+ LOC)
- Minimize API and infrastructure costs

### Non-Goals
- Code modification, refactoring, or compilation
- Real-time incremental re-indexing (codebase is static)
- Multi-language support beyond FORTRAN
- Multi-user production deployment
- Full static analysis or vulnerability detection

---

## Phase 1: Problem Research

### Problem Statement

Enterprise systems running on COBOL, Fortran, and other legacy languages power critical infrastructure — banking, scientific computing, government services. These codebases contain decades of business logic, but few engineers understand them. The engineers who wrote them are retiring, and new developers face codebases with minimal documentation, unfamiliar syntax, and complex interdependencies.

**Who has this problem:** Organizations maintaining legacy Fortran/COBOL systems, new developers onboarded to legacy projects, modernization teams planning migrations.

**Severity:** High. Fortran remains dominant in scientific computing (weather modeling, physics simulations, linear algebra). NASA's NASTRAN-95 is 1,000,000+ lines of fixed-form FORTRAN — a structural analysis system completed in the early 1970s that is still studied and referenced today. It's the canonical example of a legacy codebase that's hard to navigate without tribal knowledge.

### Current Landscape

**Commercial tools:**
- **Sourcegraph Cody** — enterprise codebase search + RAG. Strong for modern languages, monorepo-scale. Weak on legacy language understanding. Enterprise pricing.
- **Greptile** — purpose-built codebase comprehension with code graphs + RAG. Multi-hop investigation across files. $30/dev/month. No specific legacy language support.
- **GitHub Copilot** — implicit RAG via workspace indexing. Weak at deep cross-codebase understanding.
- **Cursor** — AI-native editor with codebase indexing. Strong for interactive coding, weaker at structural analysis of unfamiliar codebases.

**Open source:**
- **Code-Graph-RAG** — Tree-sitter parsing + knowledge graphs + vector search. Works as MCP server. Multi-language but legacy grammar support is immature.
- **PicoCode** — self-hosted local codebase RAG assistant. Lightweight but no code-structure awareness.

**Academic:**
- **LegacyGuard** — hybrid LLM + static analysis + RAG for vulnerability detection in legacy code (including Fortran).
- **cAST (EMNLP 2025)** — AST-based chunking for code RAG, language-invariant approach using Tree-sitter.

### Why These Fall Short for Legacy Code

1. **Embedding models are trained on modern languages** — Python/JS/Java dominate training data. Fortran semantic similarity is weaker.
2. **AST parsers have immature legacy grammars** — Tree-sitter has a Fortran grammar but it's less battle-tested than Python/JS grammars.
3. **Function-centric chunking misses Fortran idioms** — COMMON blocks, IMPLICIT typing, EQUIVALENCE statements, and Fortran's column-sensitive formatting need special handling. Fixed-form F77 has no MODULE system.
4. **No tool handles cross-system dependencies** — Fortran programs often depend on Makefiles, INCLUDE files, and preprocessor macros. NASTRAN-95 predates ISO_C_BINDING (F2003).

### Why Now

- LLM context windows and embedding models have matured enough to make code RAG viable
- Voyage code-3 (Dec 2024) significantly improved code-specific embeddings
- Hybrid search (BM25 + vector) compensates for weak legacy language embeddings
- The spec requires building this as a one-week sprint with a real legacy codebase

### Target Users and Use Cases

1. **New developer onboarding** — "Where is the main entry point?" / "What does this subroutine do?"
2. **Code navigation** — "What functions modify COMMON block X?" / "Show me all I/O operations"
3. **Dependency understanding** — "What calls this function?" / "What would break if I change this?"
4. **Documentation generation** — Explain undocumented subroutines in plain English
5. **Pattern detection** — Find similar code patterns across the codebase

---

## Phase 2: Constraints Definition

### Scale & Performance

| Constraint | Value |
|-----------|-------|
| Target codebase size | 1,000,000+ LOC across hundreds of files (NASTRAN-95). Can scope to a subset for MVP. |
| Query latency target | <3 seconds end-to-end |
| Ingestion throughput | 10,000+ LOC in <5 minutes |
| Retrieval precision | >70% relevant chunks in top-5 |
| Concurrent users | Single user (CLI tool) |
| Codebase coverage | 100% of files indexed |

### Reliability

| Constraint | Value |
|-----------|-------|
| Cost of wrong answer | Low-medium (developer tool, not production system) |
| Verification needs | File/line references must be accurate |
| Human-in-the-loop | Not required — informational tool |
| Answer accuracy | Correct file/line references are non-negotiable |

### Budget & Timeline

| Constraint | Value |
|-----------|-------|
| Timeline | 1 week (MVP in 24 hours) |
| API budget | Minimize — free tiers wherever possible |
| Infra budget | Free or near-free hosting |
| Embedding costs | Must be sustainable for re-indexing during development |

### Team & Skills

| Constraint | Value |
|-----------|-------|
| Team size | Solo developer |
| RAG framework experience | No prior RAG pipeline experience |
| Fortran experience | Limited — the tool helps bridge this gap |
| Python experience | Comfortable with Python; no FastAPI or CLI framework experience assumed |

### AI-Agent Specific Constraints

| Constraint | Value |
|-----------|-------|
| Data sensitivity | Open source code — can send to external APIs |
| LLM cost budget | Minimize per-query cost; prefer cheaper models for answer generation |
| Verification | File paths and line numbers must map to actual source code |
| Eval approach | Test with 6 reference queries from spec + custom Fortran-specific queries |

---

## Phase 3: Architecture Discovery

### Language / Runtime: Python

| Option | Pros | Cons |
|--------|------|------|
| Python | Richest RAG ecosystem (LangChain, LlamaIndex, Haystack). All embedding APIs have Python SDKs first. Strong CLI libraries (Click/Typer/Rich). Tree-sitter has mature Python bindings. Most RAG tutorials/examples are Python. | Slower ingestion than compiled languages. GIL limits true parallelism for CPU-bound parsing. |
| TypeScript/Node | Good for web-first tools. Growing RAG ecosystem (LangChain.js). Strong if frontend is the primary interface. | RAG framework ecosystem is 6-12 months behind Python equivalents. Fewer code-specific RAG examples. Tree-sitter bindings exist but less documented. |
| Rust | Fastest ingestion/parsing by far. Qdrant client is Rust-native. Memory safety for long-running processes. | Smallest RAG ecosystem — no equivalent to LlamaIndex/LangChain. Must build most pipeline components from scratch. Steeper learning curve. |
| Go | Fast compilation, good concurrency model. Simple deployment (single binary). | Minimal RAG ecosystem. No equivalent to LlamaIndex. Would require building pipeline from scratch. |

**Selected:** Python
**Rationale:** The RAG ecosystem advantage is decisive — LlamaIndex, LangChain, and Haystack all are Python-first with the most integrations, examples, and community support. Every embedding API (Voyage, OpenAI, Cohere) and vector DB client (ChromaDB, Qdrant, Pinecone) has Python as the primary SDK. For a 1-week timeline, ecosystem maturity matters more than raw performance.

### RAG Framework: LlamaIndex

| Option | Pros | Cons |
|--------|------|------|
| LlamaIndex | Purpose-built for RAG. Best document/chunk abstractions. Built-in ingestion pipeline with node parsers, metadata extractors, and index types. Native hybrid search support. CodeSplitter using tree-sitter built in. Largest RAG-specific community. | Opinionated — harder to customize when defaults don't fit. Less flexible for agentic workflows. Heavier dependency footprint. |
| LangChain | Most extensive integration catalog (700+ integrations). Largest overall community. Good documentation. LangSmith integration for observability. More flexible for custom pipelines. | General-purpose — RAG-specific abstractions require more assembly. Ingestion pipeline is less polished than LlamaIndex (no built-in CodeSplitter). Frequent API changes between versions. |
| Haystack (deepset) | Production-grade pipeline architecture. Strong built-in evaluation tools. Clean component-based design. | Smallest community of the three. Fewer code-specific integrations. Less third-party content/tutorials. |
| Custom pipeline | Full control over every component. No framework overhead or version churn. Easier to debug. | Must build ingestion, chunking, retrieval, re-ranking from scratch. No built-in integrations with vector DBs or embedding APIs. Highest development time. |

**Selected:** LlamaIndex
**Rationale:** LlamaIndex's built-in CodeSplitter (tree-sitter based) and ingestion pipeline primitives (node parsers, metadata extractors, index types) directly address the core challenge of this project: getting code chunking and retrieval right. For a RAG-focused project (not an agentic one), LlamaIndex's purpose-built abstractions reduce the amount of custom code needed compared to assembling the same from LangChain components. Haystack is a strong alternative but has fewer code-specific features.

### Vector Database: ChromaDB (MVP) → Qdrant (production)

| Option | Pros | Cons |
|--------|------|------|
| ChromaDB | Zero-cost, embedded (no server). Fastest setup — `pip install chromadb`. Perfect for CLI tool (runs locally). LlamaIndex has native integration. | No hybrid search (BM25 + vector). Limited filtering compared to Qdrant. Not production-grade for multi-user. |
| Qdrant | Open source, self-hostable. Powerful metadata filtering (critical for file path / language / function name filters). Hybrid search via "Universal Query API". Fast (Rust-based). | Requires running a server (Docker). More setup than ChromaDB for a CLI tool. Free cloud tier is small. |
| Pinecone | Managed, zero-ops. Free starter tier (2GB). | Managed-only — requires internet for every query. Overkill for a single-codebase CLI tool. Vendor lock-in. |
| pgvector | Free, SQL-based filtering is powerful. Familiar if you know Postgres. | Requires a Postgres instance. No native hybrid search. More ops overhead than ChromaDB for a CLI tool. |
| Weaviate | Native hybrid search (BM25 + vector). GraphQL API. | No free cloud tier since Oct 2025. Self-hosted requires Docker. Heavier than ChromaDB for prototyping. |

**Selected:** ChromaDB for MVP, Qdrant for production
**Rationale:** ChromaDB is the fastest path to a working MVP — embedded, zero-config, pip-installable. For a CLI tool that runs locally, there's no need for a server. Qdrant becomes the upgrade path when we need hybrid search (critical for Fortran keyword matching) and production metadata filtering. The migration path from ChromaDB to Qdrant via LlamaIndex abstractions is straightforward.

### Embedding Model: Voyage code-3

| Option | Pros | Cons |
|--------|------|------|
| Voyage code-3 | State-of-the-art for code retrieval (13-17% better than alternatives on benchmarks). 32K context window. Optimized specifically for code. Matryoshka dimensionality reduction for cost savings. | API cost (~$0.06/1M tokens for code-3). Requires API key. Less Fortran-specific training data than modern languages. |
| OpenAI text-embedding-3-small | Cheapest option ($0.02/1M tokens). Good enough for prototyping. Native OpenAI ecosystem. | Not code-optimized. Significantly weaker retrieval quality for code. 8K context window. |
| OpenAI text-embedding-3-large | Better quality than small variant. Dimensionality reduction supported. | Still not code-optimized. 3x cost of small for modest improvement on code. |
| Cohere embed-v3 | Strong multilingual support. Good general retrieval. | Not code-specific. Less accurate on code benchmarks than Voyage. |
| sentence-transformers (local) | Free, runs locally. No API dependency. | Significantly weaker embeddings. Slow on CPU. No code-specific models match Voyage quality. |

**Selected:** Voyage code-3
**Rationale:** Code-specific retrieval quality is the single most important factor for this project. Voyage code-3 leads benchmarks by 13-17% over alternatives. For a 10K-50K LOC codebase, total embedding cost is negligible (<$1). The 32K context window handles large Fortran subroutines without truncation. We'll supplement with BM25/keyword search when we upgrade to Qdrant to compensate for potential Fortran-specific embedding gaps.

### LLM for Answer Generation: GPT-4o-mini (default) / Claude Sonnet (complex)

| Option | Pros | Cons |
|--------|------|------|
| GPT-4o-mini | Extremely cheap ($0.15/1M input, $0.60/1M output). 128K context window — more than sufficient for retrieved code context. Fast responses (<1s typical). Good code understanding for synthesis tasks. Strong function calling. | Not the strongest at complex multi-step code reasoning. May miss subtle Fortran nuances that top-tier models catch. |
| Claude 4.6 Sonnet | Best-in-class code understanding. 200K context window. Excels at explaining unfamiliar/legacy code. Strong reasoning about code structure. | ~$3/1M input, $15/1M output — 20x more expensive than GPT-4o-mini. Higher latency. |
| Claude 4.5 Haiku | Cheap ($0.80/1M input, $4/1M output). Fast. Good for simple explanations. | Weaker at complex code reasoning than Sonnet. 5x more expensive than GPT-4o-mini for comparable capability tier. |
| GPT-4o | Strong code understanding. 128K context. Good function calling. | $2.50/1M input, $10/1M output — expensive without clear advantage over Sonnet for code explanation. |
| Local (Llama 3.3 70B / Mistral) | Free after hardware. Full privacy. No API dependency. | Requires GPU (16GB+ VRAM). Significantly weaker code understanding than API models. Setup and maintenance overhead. |

**Selected:** GPT-4o-mini as default, Claude Sonnet as optional upgrade for complex queries
**Rationale:** The "minimize costs" constraint is decisive. GPT-4o-mini is 20x cheaper than Sonnet and the primary task — synthesizing an answer from already-retrieved code chunks — doesn't require top-tier reasoning. The heavy lifting is in retrieval quality (embedding model + chunking), not generation. GPT-4o-mini's 128K context window handles large Fortran contexts. For users who need deeper code reasoning (e.g., explaining complex subroutine interactions), Claude Sonnet is available as a flag (`--model sonnet`). This tiered approach minimizes default costs while preserving quality as an option.

### Chunking Strategy: Regex-based FORTRAN splitter (primary) + Tree-sitter (secondary)

**This is the most critical decision in the project.** Embedding quality is only as good as the chunks we feed it. NASTRAN-95 is entirely fixed-form FORTRAN (F77 era), which changes the calculus significantly.

#### Why NASTRAN-95 changes the chunking decision

NASTRAN-95 is **fixed-form FORTRAN**: columns 1-6 are special (labels, continuation), code lives in columns 7-72. The main tree-sitter-fortran grammar only handles **free-form** (F90+). A separate `tree-sitter-fixed-form-fortran` grammar exists but is less mature. Since our entire target codebase is fixed-form, we need a chunking strategy that works reliably for F77.

#### NASTRAN-95 code characteristics
- **1M+ lines** of fixed-form FORTRAN
- **One subroutine/function per file** is common but not universal
- **COMMON blocks everywhere** — shared state across program units with no module system
- **GOTO-based control flow** — statement labels in columns 1-5
- **Heavy comments** — 50-60% of lines are documentation (critical retrieval signal)
- **No MODULE or USE statements** — F77 predates the module system
- **ENTRY statements** — multiple entry points per subroutine
- **INCLUDE files** — preprocessor-style code sharing
- **EQUIVALENCE statements** — memory aliasing (complicates variable tracking)

#### Alternatives evaluated

| Option | Pros | Cons |
|--------|------|------|
| Regex-based FORTRAN splitter | Handles fixed-form natively. Simple to build for F77 (SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA boundaries are unambiguous). Can extract COMMON blocks, CALL statements, ENTRY points as metadata. No external parser dependency. Easy to debug and tune. | No AST — can't understand nested constructs. Must handle continuation lines (column 6) manually. Less precise than a real parser for complex cases. |
| Tree-sitter (free-form grammar) | Production-grade parser. 200+ node types. LlamaIndex CodeSplitter integration. | **Does not parse fixed-form FORTRAN.** Would require converting NASTRAN's entire codebase from fixed to free-form first. |
| Tree-sitter (fixed-form grammar) | Handles fixed-form column rules. Proper AST output. | Less mature (fewer contributors, less testing). May fail on NASTRAN's vintage F66/F77 idioms. Adds complexity for uncertain benefit. |
| Fixed-to-free conversion + tree-sitter | Get AST quality for fixed-form code. Tools exist (bast/freestyle). | Adds a conversion step. Line number mapping becomes complex. Conversion may fail on unusual NASTRAN constructs. Two points of failure. |
| fsource (Python Fortran analysis) | Pure Python. Designed for static analysis. Handles both forms. | Less documented. Smaller community. May not handle all NASTRAN idioms. |
| Fixed-size + overlap | Works for any language. Zero parsing. | Splits subroutines mid-logic. Poor retrieval quality. Unacceptable for a code understanding tool. |

**Selected:** Regex-based FORTRAN splitter as primary, tree-sitter fixed-form as optional upgrade
**Rationale:** NASTRAN-95 is entirely fixed-form F77 with straightforward structure: subroutines and functions are clearly delimited by `SUBROUTINE name` / `END` patterns. A regex splitter handles this reliably and is easy to debug when chunks look wrong. The regex approach also makes metadata extraction natural — COMMON blocks, CALL statements, ENTRY points, and INCLUDE directives are all extractable with simple patterns. Tree-sitter fixed-form grammar is an upgrade path if regex proves insufficient, but for F77 code with one-subroutine-per-file conventions, regex is sufficient and more predictable.

#### Chunking implementation detail

**Step 1: Preprocessing**
- Join continuation lines (column 6 non-blank → append to previous line)
- Normalize case for parsing (FORTRAN is case-insensitive)
- Preserve original line numbers for metadata

**Step 2: Split at program unit boundaries**
- Pattern: `^\s{6}\s*(SUBROUTINE|FUNCTION|PROGRAM|BLOCK\s*DATA)\s+(\w+)` (case-insensitive)
- End pattern: `^\s{6}\s*END\s*$` or `^\s{6}\s*END\s+(SUBROUTINE|FUNCTION|PROGRAM)`
- Each program unit becomes one chunk (most NASTRAN subroutines are 100-500 lines, fitting within embedding context)

**Step 3: Handle oversized chunks**
- If a subroutine exceeds ~1500 tokens, split at logical boundaries (labeled sections, comment block separators)
- Prepend the subroutine signature and key declarations to each sub-chunk for context

**Step 4: Metadata extraction per chunk**

| Metadata | Regex Pattern | Purpose |
|----------|--------------|---------|
| `unit_name` | `(SUBROUTINE\|FUNCTION)\s+(\w+)` | Primary search key |
| `unit_type` | From the match above | Classification |
| `common_blocks` | `COMMON\s*/(\w+)/` | Cross-file shared state tracking |
| `calls` | `CALL\s+(\w+)` | Call graph |
| `entry_points` | `ENTRY\s+(\w+)` | Multiple entry subroutines |
| `includes` | `INCLUDE\s+'([^']+)'` | File dependencies |
| `externals` | `EXTERNAL\s+(.+)` | External procedure declarations |
| `file_path` | From file system | Source location |
| `line_start/end` | From preprocessing | Code location |
| `comment_ratio` | Count of `C`/`c`/`*` column-1 lines | Documentation quality signal |

**Step 5: COMMON block cross-reference index**
COMMON blocks are the F77 equivalent of shared global state. Build a separate index:
- Map each COMMON block name → list of (file, subroutine) that reference it
- Map each COMMON block → its variable list
- This enables queries like "What subroutines share data through COMMON /XYZZY/?"

#### Chunk size guidance

| Scenario | Target | Approach |
|----------|--------|----------|
| Typical subroutine (100-500 lines) | Single chunk | Keep whole — natural semantic unit |
| Small utility function (<50 lines) | Single chunk | May merge with adjacent small functions from same file |
| Large subroutine (500-3000+ lines) | Split at labeled sections | Prepend signature + declarations to each sub-chunk |
| Comment-heavy file (>60% comments) | Keep comments with code | Comments are the best retrieval signal in underdocumented FORTRAN |
| BLOCK DATA units | Single chunk | Small, self-contained data initialization |

### Observability: LangSmith

| Option | Pros | Cons |
|--------|------|------|
| LangSmith | Free developer tier (5K traces/month). Built-in eval framework with dataset management. RAG-specific metrics (retrieval precision, faithfulness). LlamaIndex integration via callback handler. Largest community for LLM observability. | Primarily LangChain-oriented — LlamaIndex integration exists but is second-class. Managed service only (data leaves your machine). |
| Braintrust | Strong eval/scoring framework. CI integration for automated eval runs. Good prompt versioning. | Smaller community than LangSmith. Less RAG-specific tracing. Free tier is more limited. |
| Langfuse | Open source, self-hostable (full data control). Good tracing UI. Growing community. | Requires self-hosting for free usage (Docker). Eval framework is less mature than LangSmith. More setup time. |
| Custom logging (structlog + files) | Zero cost. Full control. No external dependencies. | Must build tracing, eval, and dashboards from scratch. No retrieval quality metrics out of the box. |

**Selected:** LangSmith
**Rationale:** The free tier (5K traces/month) covers a single-user development workflow. The built-in eval framework with dataset management directly supports the spec's requirement for 50+ test cases and retrieval quality measurement. LlamaIndex has a callback handler integration, making setup minimal. Langfuse is a strong open-source alternative but adds Docker setup overhead that doesn't align with the 1-week timeline.

### Frontend: CLI (Typer) → Web UI later

| Option | Pros | Cons |
|--------|------|------|
| Typer CLI | Fast to build. Rich terminal output (via Rich library). Syntax highlighting for code snippets. No server needed. Perfect for developer tool UX. | No visual code navigation. Harder to show complex dependency graphs. |
| React web app | Rich UI. Syntax highlighting. File tree navigation. Can show dependency graphs visually. | Full frontend build setup. Slower to iterate. Overkill for MVP. |
| Streamlit | Fastest web UI. Good for prototypes. Built-in code display. | Limited customization. Feels like a demo, not a tool. |
| Textual (TUI) | Rich terminal UI with widgets. Can show file trees, panels. | Niche library. More complex than Typer for simple Q&A. |

**Selected:** Typer CLI (MVP), React web UI (post-MVP if time permits)
**Rationale:** CLI-first matches the developer workflow — run queries from the terminal where you're already working. Typer + Rich gives syntax-highlighted code output with file/line references. The spec accepts CLI or web, and CLI ships faster.

### Hosting / Deployment: Render (free tier) + CLI (local)

| Option | Pros | Cons |
|--------|------|------|
| Render | Free tier for web services (750 hours/month). Auto-deploys from GitHub. Native Python/Docker support. Simple setup. Spins down after inactivity (acceptable for demo). | Cold starts after spin-down (~30s). Free tier has limited RAM (512MB). |
| Railway | Simple deploy. Good Python/Docker support. $5/month hobby plan. Persistent services (no cold starts). | No free tier — costs money from day one. Overkill for a demo/submission requirement. |
| Fly.io | Free tier (3 shared VMs). Global edge deployment. Docker-native. Persistent volumes for ChromaDB data. | More complex setup (flyctl CLI, fly.toml config). Requires Dockerfile. Free tier resource limits are tight. |
| Vercel | Best-in-class for frontend deployment. Free tier is generous. | Python support is limited to serverless functions. Not ideal for long-running ingestion or processes that need persistent state. |
| Docker Hub + README | Zero hosting cost. Users run locally. Full control. | Not "deployed and publicly accessible" per spec requirement. |

**Selected:** Render (free tier) for web API + CLI (local) for primary use
**Rationale:** The spec requires "deployed and publicly accessible." Render's free tier satisfies this at zero cost — the API is a demo/submission requirement, not a production service. Cold starts after spin-down are acceptable since this isn't a latency-critical production deployment. The primary UX is the CLI tool running locally. Railway and Fly.io are stronger for always-on services but cost money, which conflicts with the "minimize costs" constraint.

### Testing Strategy: Pytest + LangSmith evals

| Option | Pros | Cons |
|--------|------|------|
| Pytest unit + integration | Industry standard for Python. Fast execution. Can test ingestion, chunking, retrieval individually. Rich assertion library. | Doesn't test end-to-end RAG quality. |
| LangSmith evals | Purpose-built for RAG evaluation. Measures retrieval precision, answer accuracy. Dataset management. | Requires test dataset creation. API calls for each eval run. |
| Ragas | Open source RAG evaluation framework. Metrics: faithfulness, relevance, context recall. | Additional dependency. Less integrated than LangSmith. |
| Manual testing | Quick sanity checks. | Not reproducible. Doesn't scale. |

**Selected:** Pytest (unit/integration) + LangSmith evals (RAG quality)
**Rationale:** Pytest for deterministic tests (chunking correctness, metadata extraction, API contracts). LangSmith evals for measuring retrieval precision and answer quality against the 6 reference queries from the spec. This two-layer approach covers both correctness and quality.

---

## Phase 4: Solution Design

### Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                    CLI (Typer)                    │
│  legacylens ingest <path>  |  legacylens ask "?" │
└───────────┬──────────────────────┬───────────────┘
            │                      │
    ┌───────▼───────┐      ┌──────▼──────┐
    │   Ingestion   │      │  Retrieval  │
    │   Pipeline    │      │  Pipeline   │
    │               │      │             │
    │ File Discovery│      │ Query Embed │
    │ Preprocessing │      │ Vector Search│
    │ Regex Chunking│      │ Re-ranking  │
    │ Metadata Ext. │      │ Context Asm.│
    │ Embedding     │      │ LLM Answer  │
    │ Storage       │      │             │
    └───────┬───────┘      └──────┬──────┘
            │                      │
    ┌───────▼──────────────────────▼──────┐
    │         ChromaDB (embedded)          │
    │   Vectors + Metadata per chunk       │
    └─────────────────────────────────────┘
            │                      │
    ┌───────▼───────┐      ┌──────▼──────┐
    │  Voyage code-3│      │ GPT-4o-mini │
    │  (embeddings) │      │(generation) │
    └───────────────┘      └─────────────┘
```

### Two-Phase Architecture

The NASTRAN-95 codebase is static — it's a 1970s-era codebase released as open source, with no active development. This means ingestion and querying are completely decoupled phases with no need for incremental updates, change detection, or real-time re-indexing.

**Phase A: Ingest (run once, store permanently)**

This is a batch job that runs to completion before any queries happen. We can optimize aggressively — take as long as needed, use all available resources, validate thoroughly.

1. `legacylens ingest ./NASTRAN-95/` scans directory for `.f`, `.for`, `.ftn` files (fixed-form FORTRAN)
2. Preprocessor joins continuation lines (column 6), normalizes case, tracks original line numbers
3. Regex-based splitter chunks at SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA boundaries
4. Metadata extractor captures: file_path, line_start, line_end, unit_name, unit_type, common_blocks, calls
6. Voyage code-3 generates embeddings per chunk (batch all at once — no streaming needed)
7. ChromaDB stores vectors + metadata to persistent directory
8. **Validation pass** — verify chunk count, metadata completeness, spot-check embeddings
9. Print ingestion summary: files processed, chunks created, total tokens embedded, cost

Once ingestion completes, the ChromaDB directory is a static artifact. It can be committed, shipped, or copied — no database server needed.

**Phase B: Search & Answer (runs against the static index)**

Pure read-only queries against the pre-built index. Fast, cheap, repeatable.

1. `legacylens ask "What functions handle memory allocation?"` embeds the query via Voyage code-3
2. ChromaDB similarity search returns top-k chunks with metadata
3. Context assembler combines chunks with surrounding code context (±N lines)
4. GPT-4o-mini generates answer with file/line references from metadata (or Claude Sonnet via `--model sonnet`)
5. CLI renders answer with syntax-highlighted code snippets (Rich library)

**Why this matters:**
- **Embedding costs are one-time.** We pay to embed the codebase once, then query as many times as we want for just the cost of a single query embedding + LLM call.
- **No consistency concerns.** The index always matches the source code because the source code doesn't change.
- **Pre-built index can ship with the project.** Users can skip ingestion entirely if we include the ChromaDB directory. Estimated index size for 1M LOC: ~200-500MB (vectors + metadata), feasible for git-lfs or a release artifact.
- **Testing is clean.** We ingest once, then run the full eval suite against the same static index — deterministic, reproducible results.

### Data Model

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

ChromaDB stores each chunk with: `id` = `"{file_path}:{line_start}"`, `document` = chunk text, `embedding` = Voyage code-3 vector, `metadata` = all fields above (lists stored as JSON-encoded strings since ChromaDB metadata is flat).

### Error Handling

- **Ingestion errors:** If a file fails to parse, log the error and continue with remaining files. Print a summary of skipped files at the end. Exit code 0 if any files succeeded, non-zero if all failed.
- **Embedding API failures:** Retry with exponential backoff (3 attempts). If a batch fails after retries, skip those chunks and log them for manual review.
- **Query failures:** If embedding or LLM API is unavailable, print a clear error message with the service name and suggest checking API keys / network.
- **Partial ingestion:** Track which files have been successfully embedded. Support resumable ingestion (skip already-stored chunks on re-run).

### Key Integration Points

| Integration | Protocol | Purpose |
|-------------|----------|---------|
| Voyage AI API | HTTPS | Embedding generation (ingest + query) |
| OpenAI API | HTTPS | Answer generation (GPT-4o-mini default, Claude Sonnet optional) |
| ChromaDB | In-process (Python) | Vector storage + retrieval |
| LangSmith | HTTPS (callback) | Tracing + eval |

### MVP Scope vs Full Scope

**MVP (24 hours):**

*Phase A — Ingest (do first, get right):*
- Ingest NASTRAN-95 source files (full codebase or scoped subset)
- Regex-based chunking with metadata (file path, line numbers, unit names, COMMON blocks, calls)
- Generate and store all embeddings in ChromaDB
- Validation pass: verify coverage, spot-check chunks

*Phase B — Search & Answer (build against static index):*
- Semantic search (vector-only)
- Basic answer generation with file/line references
- CLI interface (`ingest` + `ask` commands)
- 6 test queries from spec working

**Full scope (1 week):**
- Hybrid search (BM25 + vector) via Qdrant upgrade
- 4+ code understanding features (explanation, dependency mapping, pattern detection, documentation gen)
- Web API on Render for public access
- LangSmith eval suite with 50+ test cases
- Re-ranking for improved retrieval precision
- Pre-built index shipped with project (users skip ingestion)
- Cost analysis document

---

## Phase 5: Risk & Refinement

### Failure Modes

| Failure | Likelihood | Mitigation |
|---------|-----------|------------|
| Regex splitter misses edge cases | Medium | Validation pass after ingestion. Manual spot-checks. Tree-sitter fixed-form grammar as upgrade path. |
| Embeddings weak on Fortran semantics | Medium-High | Hybrid search (add BM25/keyword) in Qdrant upgrade. Metadata filtering by function name. |
| Large subroutines exceed chunk size | Low | Configurable max chunk size with overlap. Split large functions at logical boundaries. |
| Incorrect file/line references | Medium | Store absolute line numbers in metadata during ingestion. Verify at retrieval time. |
| NASTRAN-95 codebase too large for MVP (1M+ LOC) | Medium | Scope to a subset (e.g., one module/subsystem directory) for MVP, expand after pipeline is validated |
| Voyage API rate limits during ingestion | Low | Batch embedding calls. Add retry with backoff. |

### Security Considerations

| Concern | Mitigation |
|---------|------------|
| Sending code to external APIs | Target is open source (NASA NASTRAN-95, NASA Open Source Agreement) — no proprietary code risk |
| API key management | `.env` file, not committed. Render env vars for deployment. |
| Prompt injection via code comments | Low risk — code is the source of truth, not user-generated |
| Data leakage | CLI runs locally. Only embeddings and queries hit external APIs. |

### Testing Strategy

**Unit tests (Pytest):**
- Chunking: verify regex splitter produces valid chunks with correct boundaries and metadata
- Metadata extraction: file paths, line numbers, function names are accurate
- Ingestion pipeline: end-to-end from file to ChromaDB storage

**Integration tests:**
- Query pipeline: question → embedding → retrieval → answer
- File/line reference accuracy: retrieved chunks map to actual source lines

**Eval suite (LangSmith):**
- 6 reference queries from spec (entry point, function search, code explanation, I/O ops, dependencies, patterns)
- 44+ additional queries covering edge cases, multi-file dependencies, Fortran-specific constructs
- Metrics: retrieval precision@5, answer faithfulness, reference accuracy

### Deployment & Ops

- **CLI:** Distributed via pip (`pip install legacylens`), or just clone + `uv run`
- **Web API:** FastAPI on Render (free tier) for public access requirement
- **Monitoring:** LangSmith tracing for all queries
- **Rollback:** Git-based. No stateful infrastructure beyond ChromaDB (which is file-based and can be regenerated by re-ingesting)

### Iteration Plan

1. **Day 1 (MVP):**
   - Phase A: Ingest NASTRAN-95 → validate chunks → store embeddings (get this right first)
   - Phase B: Build query pipeline against the static index → 6 test queries passing
2. **Day 2:** Improve chunking quality based on retrieval results. Re-ingest if needed (one-time cost, cheap to redo). Add code understanding features.
3. **Day 3:** Build eval suite (50+ test cases). Measure retrieval precision. Upgrade to Qdrant + hybrid search if precision < 70%.
4. **Day 4-5:** Deploy web API to Render. Polish CLI. Ship pre-built index. Documentation, cost analysis, eval results.

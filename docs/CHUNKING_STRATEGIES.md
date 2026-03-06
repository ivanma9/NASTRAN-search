# LegacyLens — Chunking Strategies

**Date:** 2026-03-03
**Codebase:** NASA NASTRAN-95 (1M+ LOC, fixed-form FORTRAN 77)

---

## Why Chunking Matters

Chunking is the most critical decision in a code RAG system. Embedding quality is only as good as the chunks fed into it. Poor boundaries — splitting a subroutine mid-logic, separating a function from its declarations — destroy retrieval precision regardless of how good the embedding model is.

NASTRAN-95 compounds the challenge: it's entirely **fixed-form FORTRAN** (F77 era) with column-sensitive formatting, continuation lines in column 6, COMMON block shared state, GOTO-based control flow, and no module system. Generic chunking strategies built for modern languages fail here.

---

## Strategy Overview

| Strategy | Use Case | Status |
|----------|----------|--------|
| **Function-level (Program Unit Boundary)** | Each SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA as a chunk | **Implemented** (primary) |
| **Oversized splitting** | Sub-chunk large units that exceed token limits | **Implemented** (secondary) |
| **Fixed-form preprocessing** | Join continuation lines before chunking | **Implemented** (prerequisite) |
| **Metadata enrichment** | Post-chunk extraction of COMMON blocks, calls, etc. | **Implemented** (post-processing) |
| **Paragraph-level (COBOL)** | COBOL PARAGRAPH as natural boundary | Not applicable (FORTRAN codebase) |
| **Fixed-size + overlap** | Fallback for unstructured sections | Evaluated, rejected (see below) |
| **Semantic splitting (LLM)** | Use LLM to identify logical boundaries | Not implemented (see below) |
| **Hierarchical** | Multiple granularities (file > section > function) | Partial (unit + sub-chunk) |

---

## Strategy 1: Function-Level (Program Unit Boundary Splitting)

**Status:** Primary strategy, implemented in `src/legacylens/ingest/chunker.py`

### How It Works

FORTRAN 77 programs are organized into **program units** — discrete blocks delimited by clear keywords. Each unit becomes one chunk:

```
SUBROUTINE name ... END
FUNCTION name ... END
PROGRAM name ... END
BLOCK DATA name ... END
```

The chunker scans preprocessed source line-by-line, detecting unit headers via regex and flushing accumulated lines at each boundary.

### Regex Patterns

```python
# Standard unit headers
UNIT_START_RE = re.compile(
    r"^\s*(SUBROUTINE|FUNCTION|PROGRAM|BLOCK\s*DATA)\s+(\w+)",
    re.IGNORECASE,
)

# Typed functions (e.g., INTEGER FUNCTION FOO)
TYPED_FUNC_RE = re.compile(
    r"^\s*(?:INTEGER|REAL|DOUBLE\s*PRECISION|COMPLEX|LOGICAL|CHARACTER)"
    r"\s+FUNCTION\s+(\w+)",
    re.IGNORECASE,
)

# Unit terminator
UNIT_END_RE = re.compile(r"^\s*END\s*$", re.IGNORECASE)
```

### Why This Works for NASTRAN-95

- NASTRAN follows a **one-subroutine-per-file** convention (common but not universal)
- Program unit boundaries (`SUBROUTINE ... END`) are unambiguous in F77
- Most subroutines are 100-500 lines, fitting within the 1,500-token embedding budget
- Comments are preserved with their associated code — critical since 50-60% of lines are documentation

### Production Results

| Metric | Value |
|--------|-------|
| Source files indexed | 1,848 |
| Total chunks produced | 4,520 |
| Unique unit names | 1,856 |
| Retrieval precision@5 | 93% (13/14 benchmark queries) |

### Chunk Filtering

After splitting, chunks are validated and filtered:

- **Empty/whitespace-only chunks** — discarded
- **Tiny chunks** (<10 characters or <5 tokens) — discarded
- **Comment-only chunks** (no executable code) — discarded
- **Token counting** — uses `tiktoken` (CL100K_BASE) with fallback to `len(text) // 4`

---

## Strategy 2: Oversized Chunk Splitting

**Status:** Implemented in `chunker.py:_split_oversized()`

### Problem

Some NASTRAN subroutines exceed 1,500 tokens (the configured `chunk_max_tokens` limit). Embedding models perform best with focused, coherent chunks — a 3,000-token subroutine dilutes the semantic signal.

### Approach

When a chunk exceeds `max_tokens`:

1. **Find the signature line** — the first non-comment, non-empty line (usually the `SUBROUTINE` declaration)
2. **Accumulate lines** until the token count exceeds the limit
3. **Split at the current position**, creating a sub-chunk from accumulated lines
4. **Prepend signature** to continuation chunks with a `C     ... (continued)` marker
5. **Repeat** until all lines are consumed

### Design Decisions

- **Signature replication, not sliding window overlap:** Each continuation sub-chunk gets the subroutine signature prepended, providing context without duplicating large blocks of code
- **All sub-chunks retain the parent's `unit_name`:** Ensures retrieval for a subroutine name finds all its parts
- **Minimum split size:** Won't split if fewer than 10 lines accumulated (prevents degenerate micro-chunks)

### Example

A 2,500-token `SUBROUTINE DCOMP` would become:

```
Chunk 1: SUBROUTINE DCOMP (lines 1-85, ~1,400 tokens)
Chunk 2: SUBROUTINE DCOMP / C ... (continued) (lines 86-150, ~1,100 tokens)
```

Both chunks are stored with `unit_name="DCOMP"` so queries about DCOMP retrieve both.

---

## Strategy 3: Fixed-Form Preprocessing

**Status:** Implemented in `src/legacylens/ingest/preprocess.py`

### Problem

Fixed-form FORTRAN has column-sensitive formatting that must be normalized before chunking:

| Columns | Purpose |
|---------|---------|
| 1 | Comment indicator (`C`, `c`, `*`, `!`) |
| 1-5 | Statement labels (numeric) |
| 6 | Continuation marker (any non-blank, non-zero character) |
| 7-72 | Statement body |
| 73-80 | Sequence numbers (ignored) |

A single logical statement can span multiple physical lines via continuation markers. Chunking raw text would break statements mid-expression.

### Approach

The `preprocess_fixed_form()` function:

1. **Detects continuation lines** — column 6 is non-blank and not `0` or `' '`
2. **Joins continuation lines** — appends columns 7+ to the current statement
3. **Normalizes case** — converts to uppercase (FORTRAN is case-insensitive)
4. **Tracks line mapping** — maintains `line_map: dict[int, int]` from preprocessed line index to original line number

### Why This is Critical

Without preprocessing:
- `SUBROUTINE` declarations split across lines wouldn't be detected
- Token counts would be inflated by continuation formatting
- Line number references in answers would be wrong

---

## Strategy 4: Metadata Enrichment (Post-Chunking)

**Status:** Implemented in `src/legacylens/ingest/metadata.py`

### Approach

After chunking, each `FortranChunk` is enriched with structural metadata extracted via regex:

| Metadata Field | Regex Pattern | Purpose |
|----------------|--------------|---------|
| `common_blocks` | `COMMON\s*/\s*(\w+)\s*/` | Cross-file shared state tracking |
| `calls` | `CALL\s+(\w+)` | Call graph construction |
| `entry_points` | `ENTRY\s+(\w+)` | Multiple entry point detection |
| `includes` | `INCLUDE\s+['"]([^'"]+)['"]` | File dependency tracking |
| `externals` | `EXTERNAL\s+(.+)` | External procedure declarations |
| `comment_ratio` | Comment line count / total lines | Documentation quality signal |
| `token_count` | `tiktoken` CL100K_BASE encoding | Embedding budget tracking |

### How Metadata Powers Retrieval

Metadata is stored alongside embeddings in ChromaDB and used at query time:

1. **Direct chunk injection** — if a query mentions a unit name (e.g., "What does DCOMP do?"), the retriever looks up the chunk by `unit_name` and prepends it to results, bypassing vector similarity
2. **COMMON block cross-reference** — queries about shared state (e.g., "What subroutines use COMMON /SYSTEM/?") use the COMMON block index built from metadata
3. **Call graph traversal** — "What calls XREAD?" is answered by traversing the call graph built from `calls` metadata
4. **Keyword re-ranking** — I/O keywords (`READ`, `WRITE`, `OPEN`) and error keywords get bonus scores during retrieval

### Indices Built from Metadata

Two JSON indices are constructed post-ingestion in `data/indices/`:

**`call_graph.json`** — Bidirectional call relationships:
```json
{
  "DCOMP": {
    "calls": ["XREAD", "WRITE"],
    "called_by": ["MAIN", "SOLVER"],
    "file": "src/dcomp.f",
    "line": 1
  }
}
```

**`common_blocks.json`** — COMMON block cross-references:
```json
{
  "/SYSTEM/": {
    "variables": ["NSYS", "NBUF", "NOUT"],
    "referenced_by": [
      {"file": "src/dcomp.f", "unit": "DCOMP", "line": 45},
      {"file": "src/xread.f", "unit": "XREAD", "line": 12}
    ]
  }
}
```

---

## Strategy 5: Paragraph-Level (COBOL)

**Status:** Not applicable to LegacyLens (FORTRAN codebase)

### Concept

COBOL programs have a natural hierarchical structure: `DIVISION > SECTION > PARAGRAPH`. Each `PARAGRAPH` is a self-contained block of logic, making it the ideal chunk boundary for COBOL RAG systems.

```cobol
PROCEDURE DIVISION.
    MAIN-PARAGRAPH.
        PERFORM VALIDATE-INPUT.
        PERFORM CALCULATE-INTEREST.
        PERFORM GENERATE-REPORT.
        STOP RUN.

    VALIDATE-INPUT.
        IF ACCOUNT-NUMBER IS NOT NUMERIC
            DISPLAY "INVALID ACCOUNT"
        END-IF.
```

### Why It Doesn't Apply Here

NASTRAN-95 is pure FORTRAN 77 — it has no COBOL-style paragraphs. The FORTRAN equivalent is the **program unit** (SUBROUTINE/FUNCTION), which is what our primary strategy uses. If LegacyLens were extended to support COBOL codebases, paragraph-level chunking would be the recommended primary strategy.

---

## Strategy 6: Fixed-Size + Overlap

**Status:** Evaluated, rejected

### Concept

Split source code into fixed-size windows (e.g., 512 tokens) with overlap (e.g., 128 tokens). Language-agnostic, zero parsing required.

### Why We Rejected It

| Concern | Impact |
|---------|--------|
| Splits subroutines mid-logic | Destroys semantic coherence |
| Separates declarations from usage | Embedding can't capture variable relationships |
| No metadata extraction possible | Chunk boundaries don't align with program structure |
| Redundant content from overlap | Wastes embedding budget |
| Poor retrieval quality | Unacceptable for a code understanding tool |

Fixed-size chunking is a reasonable **fallback** for truly unstructured text (e.g., inline documentation files without code structure), but NASTRAN-95's clean SUBROUTINE/END boundaries make it unnecessary.

### When It Would Be Useful

- Freeform documentation files with no structural markers
- Mixed-content files where program unit detection fails
- As a last-resort fallback when regex parsing encounters unexpected formatting

---

## Strategy 7: Semantic Splitting (LLM-Based)

**Status:** Not implemented

### Concept

Use an LLM to read source code and identify logical boundaries — e.g., "this block handles input validation, this block does the computation, this block writes output." The LLM determines where to split based on semantic meaning rather than syntactic markers.

### Why We Didn't Implement It

| Concern | Rationale |
|---------|-----------|
| Cost | Processing 1M+ LOC through an LLM for chunking would cost $50-200+ |
| Latency | Ingestion would take hours instead of minutes |
| Determinism | LLM boundaries would vary between runs |
| Unnecessary | F77 program units are already semantically coherent |
| Complexity | Adds an LLM dependency to the ingestion pipeline |

### When It Would Be Valuable

- **Monolithic files** with multiple logical sections but no clear syntactic boundaries
- **Mixed-paradigm code** where function boundaries don't capture logical groupings
- **Highly complex subroutines** where splitting at comment blocks (our oversized strategy) doesn't capture meaningful sections
- **Future enhancement:** Could be used selectively for the largest, most complex subroutines where the oversized splitter's comment-boundary heuristic is insufficient

---

## Strategy 8: Hierarchical Chunking

**Status:** Partially implemented

### Concept

Create chunks at multiple granularities and store them together:

```
Level 0: Entire file (file-level summary)
Level 1: Program unit (SUBROUTINE/FUNCTION)
Level 2: Logical section within a unit
Level 3: Individual statement or declaration
```

### Current Implementation

LegacyLens implements **two levels** of this hierarchy:

| Level | Implementation |
|-------|---------------|
| **Program unit** | Primary chunking at SUBROUTINE/FUNCTION boundaries |
| **Sub-unit section** | Oversized splitting creates sub-chunks within large units |

### What's Missing

- **File-level summaries** — a high-level embedding of the entire file's purpose
- **Statement-level chunks** — individual declarations or key statements
- **Parent-child linking** — sub-chunks don't reference their parent chunk ID

### Potential Enhancement

A full hierarchical approach would allow queries at different specificity levels:

| Query Type | Best Chunk Level |
|------------|-----------------|
| "What does file X do?" | File-level summary |
| "Explain subroutine DCOMP" | Program unit |
| "What variables does DCOMP declare?" | Section/declaration level |
| "What is the DO loop at line 45?" | Statement level |

---

## Data Model

All strategies feed into a single data model:

```python
@dataclass
class FortranChunk:
    text: str                    # The actual code text
    file_path: str               # Path to source file
    line_start: int              # First line in original file
    line_end: int                # Last line in original file
    unit_name: str               # e.g., "DCOMP", "XREAD"
    unit_type: str               # "subroutine" | "function" | "program" | "block_data"
    common_blocks: list[str]     # COMMON block names referenced
    calls: list[str]             # Subroutines called via CALL
    entry_points: list[str]      # ENTRY statements (secondary entry points)
    includes: list[str]          # INCLUDE file references
    externals: list[str]         # EXTERNAL declarations
    comment_ratio: float         # 0.0 - 1.0
    token_count: int             # Tokens (tiktoken CL100K_BASE)
```

Stored in ChromaDB with ID format `{file_path}:{line_start}`, enabling resumable ingestion and deduplication.

---

## Chunk Size Guidance

| Scenario | Target Size | Approach |
|----------|-------------|----------|
| Typical subroutine (100-500 lines) | Single chunk (~300-1,200 tokens) | Keep whole — natural semantic unit |
| Small utility function (<50 lines) | Single chunk (<200 tokens) | Keep as-is; no merging |
| Large subroutine (500-3,000+ lines) | Split at ~1,500 tokens | Oversized splitter with signature prepend |
| Comment-heavy file (>60% comments) | Keep comments with code | Comments are the best retrieval signal |
| BLOCK DATA units | Single chunk (small) | Self-contained data initialization |

**Default max tokens:** 1,500 (configurable via `config.py:chunk_max_tokens`)

---

## Pipeline Flow

```
NASTRAN-95 source files (.f, .for, .ftn)
        │
        ▼
┌─────────────────────┐
│  1. PREPROCESSING    │  Join continuation lines (column 6)
│     preprocess.py    │  Normalize case to uppercase
│                      │  Track original line number mapping
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  2. CHUNKING         │  Split at SUBROUTINE/FUNCTION/PROGRAM/BLOCK DATA
│     chunker.py       │  Handle oversized chunks (>1,500 tokens)
│                      │  Filter empty/tiny/comment-only chunks
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  3. METADATA         │  Extract: COMMON blocks, CALLs, ENTRY points
│     metadata.py      │  Extract: INCLUDEs, EXTERNALs, comment ratio
│                      │  Count tokens per chunk
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  4. EMBEDDING        │  Voyage code-3 (batch, 128 chunks/call)
│     embedder.py      │  1,536-dimensional vectors
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  5. STORAGE          │  ChromaDB (embedded, persistent)
│     storage.py       │  ID: file_path:line_start
│                      │  Metadata as flat key-value pairs
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  6. INDEX BUILDING   │  call_graph.json (bidirectional)
│     call_graph.py    │  common_blocks.json (cross-reference)
│     common_blocks.py │
└─────────────────────┘
```

---

## Alternatives Considered (Decision Log)

### Tree-sitter (Free-Form Grammar)

Production-grade parser with 200+ node types and LlamaIndex `CodeSplitter` integration. **Rejected** because the free-form grammar does not parse fixed-form FORTRAN — it would require converting NASTRAN's entire codebase first.

### Tree-sitter (Fixed-Form Grammar)

A separate `tree-sitter-fixed-form-fortran` grammar exists. **Deferred** as an upgrade path — it's less mature with fewer contributors and may fail on NASTRAN's vintage F66/F77 idioms. The regex approach is simpler and more predictable for our use case.

### Fixed-to-Free Conversion + Tree-sitter

Convert fixed-form to free-form (tools like `bast/freestyle` exist), then use tree-sitter. **Rejected** due to added complexity: two conversion steps, difficult line number mapping, and potential conversion failures on unusual NASTRAN constructs.

### fsource (Python Fortran Analysis)

Pure Python Fortran static analysis library that handles both forms. **Deferred** — less documented, smaller community, uncertain handling of all NASTRAN idioms.

---

## Future Enhancements

1. **Tree-sitter fixed-form grammar** — upgrade from regex if edge cases accumulate
2. **File-level summaries** — LLM-generated one-line descriptions per file for hierarchical retrieval
3. **Statement-level chunks** — for fine-grained queries about specific declarations
4. **INCLUDE file expansion** — inline included code before chunking for complete context
5. **EQUIVALENCE tracking** — memory aliasing complicates variable analysis
6. **COBOL support** — paragraph-level chunking if LegacyLens expands to COBOL codebases
7. **Selective semantic splitting** — LLM-based boundary detection for the most complex monolithic subroutines

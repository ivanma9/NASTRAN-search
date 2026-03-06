# LegacyLens

**RAG-powered system for understanding legacy FORTRAN codebases**

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://legacylens-production-bcaa.up.railway.app/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> Query NASA's NASTRAN-95 (1M+ lines of FORTRAN 77) using natural language. Get code explanations, dependency maps, and impact analysis instantly.

**Live Demo:** https://legacylens-production-bcaa.up.railway.app/

---

## Features

- **Natural Language Queries** — Ask questions about the codebase in plain English
- **Code Explanation** — Get plain-English explanations of FORTRAN subroutines
- **Dependency Mapping** — Visualize call graphs and COMMON block relationships
- **Impact Analysis** — Understand what breaks if you change a subroutine
- **FORTRAN → Python Translation** — Get modern Python equivalents with NumPy/SciPy
- **Documentation Generation** — Auto-generate technical docs for undocumented code
- **Syntax Highlighting** — NASA-themed UI with FORTRAN syntax highlighting

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface                          │
│   CLI (Typer + Rich)              Web UI (FastAPI + Vue)    │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
     ┌─────▼─────┐                  ┌─────▼─────┐
     │  Ingest   │                  │  Search   │
     │  Pipeline │                  │  Pipeline │
     └─────┬─────┘                  └─────┬─────┘
           │                              │
     ┌─────▼──────────────────────────────▼─────┐
     │              ChromaDB                     │
     │     Vectors + Metadata + Indices          │
     └─────┬──────────────────────────────┬─────┘
           │                              │
     ┌─────▼─────┐                  ┌─────▼─────┐
     │ Voyage    │                  │ GPT-4o-   │
     │ code-3    │                  │ mini      │
     └───────────┘                  └───────────┘
```

### Tech Stack

| Layer | Technology |
|-------|------------|
| Vector Database | ChromaDB (embedded) |
| Embeddings | Voyage code-3 (1536 dims) |
| LLM | GPT-4o-mini |
| Backend | FastAPI + Python 3.11 |
| Frontend | Vue 3 + Highlight.js |
| Deployment | Railway |

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Voyage AI API key ([get one free](https://www.voyageai.com/))
- OpenAI API key

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/LegacyLens.git
cd LegacyLens

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your API keys:
#   VOYAGE_API_KEY=your-voyage-key
#   OPENAI_API_KEY=your-openai-key
```

### Ingest the Codebase

```bash
# Ingest NASTRAN-95 source files (run once)
uv run legacylens ingest ./NASTRAN-95/

# Check ingestion stats
uv run legacylens stats
```

### Query via CLI

```bash
# Ask questions about the codebase
uv run legacylens ask "Where is the main entry point?"
uv run legacylens ask "What subroutines reference COMMON block /SYSTEM/?"
uv run legacylens ask "Explain what DCOMP does"
```

### Run Web UI

```bash
# Start the FastAPI server
uv run uvicorn legacylens.api:app --reload

# Open http://localhost:8000 in your browser
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ask` | POST | Query with LLM answer generation |
| `/api/ask/stream` | POST | Streaming query (SSE) |
| `/api/explain` | POST | Explain a code snippet |
| `/api/translate` | POST | FORTRAN → Python translation |
| `/api/document` | POST | Generate documentation |
| `/api/dependencies/{unit}` | GET | Get call graph + COMMON blocks |
| `/api/impact/{unit}` | GET | Impact analysis |
| `/api/status` | GET | Index statistics |
| `/api/health` | GET | Health check |

### Example Request

```bash
curl -X POST https://legacylens-production-bcaa.up.railway.app/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main entry point?", "top_k": 5}'
```

## Project Structure

```
legacylens/
├── src/legacylens/
│   ├── cli.py              # CLI commands (ingest, ask, stats, validate)
│   ├── api.py              # FastAPI endpoints
│   ├── config.py           # Settings (Pydantic)
│   ├── ingest/             # Ingestion pipeline
│   │   ├── discovery.py    # File discovery
│   │   ├── preprocess.py   # Fixed-form FORTRAN handling
│   │   ├── chunker.py      # Syntax-aware chunking
│   │   ├── metadata.py     # COMMON blocks, CALL extraction
│   │   ├── embedder.py     # Voyage code-3 embeddings
│   │   └── storage.py      # ChromaDB persistence
│   ├── search/             # Retrieval pipeline
│   │   ├── retriever.py    # Vector search + re-ranking
│   │   ├── context.py      # Context assembly
│   │   └── generator.py    # LLM answer generation
│   ├── index/              # Cross-reference indices
│   │   ├── call_graph.py   # Bidirectional call graph
│   │   └── common_blocks.py # COMMON block mapping
│   └── web/                # Frontend
│       └── index.html      # NASA-themed Vue UI
├── data/
│   ├── chromadb/           # Vector store
│   └── indices/            # JSON indices
├── tests/                  # Unit + integration tests
└── docs/                   # Architecture docs
```

## Documentation

- [Architecture & System Design](docs/ARCHITECTURE.md)
- [Chunking Strategies](docs/CHUNKING_STRATEGIES.md)
- [Performance Optimization](docs/PERFORMANCE.md)
- [AI Cost Analysis](docs/COST_ANALYSIS.md)
- [Pre-Search Research](docs/pre-search-legacylens.md)

## Performance

| Metric | Target | Achieved |
|--------|--------|----------|
| Query latency | <3s | ~2.9s avg |
| Retrieval precision | >70% top-5 | ~75% |
| Codebase coverage | 100% indexed | 100% |
| Ingestion throughput | 10K LOC / 5min | ~15K LOC / 5min |

## Cost Analysis

See [docs/COST_ANALYSIS.md](docs/COST_ANALYSIS.md) for detailed breakdown.

| Scale | Estimated Monthly Cost |
|-------|------------------------|
| 100 users | ~$15/month |
| 1,000 users | ~$120/month |
| 10,000 users | ~$950/month |
| 100,000 users | ~$8,500/month |

## Testing

```bash
# Run unit tests
uv run pytest tests/ -v

# Validate chunk quality
uv run legacylens validate --sample 20
```

## Deployment

The app is deployed on Railway at:

**https://legacylens-production-bcaa.up.railway.app/**

To deploy your own instance:

```bash
# Using Railway CLI
railway login
railway init
railway up

# Or using Docker
docker build -t legacylens .
docker run -p 8000:8000 --env-file .env legacylens
```

## License

This project is for educational purposes. NASTRAN-95 is released under the NASA Open Source Agreement.

## Acknowledgments

- NASA for releasing NASTRAN-95 as open source
- Gauntlet AI for the project specification

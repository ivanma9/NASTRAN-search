"""
FastAPI wrapper for LegacyLens RAG backend.
Exposes CLI functionality as HTTP endpoints for the web UI.
"""

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from legacylens.config import get_settings
from legacylens.search.context import assemble_context
from legacylens.search.generator import generate_answer
from legacylens.search.retriever import retrieve

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

app = FastAPI(
    title="LegacyLens API",
    description="Mission Control for NASTRAN-95 Code Analysis",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class ChunkResponse(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    unit_name: str = ""
    unit_type: str = ""
    text: str
    score: float = 0.0


class QueryResponse(BaseModel):
    answer: str
    chunks: list[ChunkResponse]


class IndexStatus(BaseModel):
    chunks: int
    unit_types: list[str] = []
    common_blocks: int = 0
    call_graph_nodes: int = 0


@app.get("/api/status", response_model=IndexStatus)
async def get_index_status():
    """Get metadata about the current ChromaDB index."""
    try:
        import chromadb

        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chromadb_path)
        collection = client.get_collection(name=settings.collection_name)
        count = collection.count()

        unit_types = []
        if count > 0:
            sample = collection.peek(10)
            unit_types = sorted(
                {m.get("unit_type", "") for m in sample["metadatas"] if m.get("unit_type")}
            )

        # Check indices
        cb_path = Path("data/indices/common_blocks.json")
        cg_path = Path("data/indices/call_graph.json")

        cb_count = 0
        cg_count = 0
        if cb_path.exists():
            cb_count = len(json.loads(cb_path.read_text()))
        if cg_path.exists():
            cg_count = len(json.loads(cg_path.read_text()))

        return IndexStatus(
            chunks=count,
            unit_types=unit_types,
            common_blocks=cb_count,
            call_graph_nodes=cg_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read index status: {e}")


@app.post("/api/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """Answer a natural language question about the NASTRAN-95 codebase."""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        results = retrieve(request.question, top_k=request.top_k)

        if not results:
            return QueryResponse(answer="No relevant code found. The index may be empty.", chunks=[])

        context = assemble_context(results)
        answer = generate_answer(request.question, context)

        chunks = []
        for r in results:
            meta = r["metadata"]
            chunks.append(
                ChunkResponse(
                    file_path=meta.get("file_path", ""),
                    line_start=meta.get("line_start", 0),
                    line_end=meta.get("line_end", 0),
                    unit_name=meta.get("unit_name", ""),
                    unit_type=meta.get("unit_type", ""),
                    text=r["text"],
                    score=r.get("score", 0),
                )
            )

        return QueryResponse(answer=answer, chunks=chunks)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "operational", "mission": "LEGACY_LENS"}


# Serve the web UI
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

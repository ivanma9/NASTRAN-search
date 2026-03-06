"""
FastAPI wrapper for LegacyLens RAG backend.
Exposes CLI functionality as HTTP endpoints for the web UI.
"""

import json
import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from legacylens.config import get_settings
from legacylens.index.call_graph import load_index as load_call_graph, get_callers, get_callees
from legacylens.index.common_blocks import find_shared_state, load_index as load_common_blocks
from legacylens.search.context import assemble_context
from legacylens.search.generator import generate_answer, generate_answer_stream, _get_openai_client
from legacylens.search.retriever import retrieve
from typing import Optional

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


class ExplainRequest(BaseModel):
    code: str
    file_path: str
    function_name: Optional[str] = None


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


class DependencyResponse(BaseModel):
    unit_name: str
    calls: list[str] = []
    called_by: list[str] = []
    common_blocks: list[str] = []
    file: str = ""
    line: int = 0


class ImpactUnit(BaseModel):
    name: str
    file: str = ""
    line: int = 0
    depth: int = 0


class ImpactResponse(BaseModel):
    unit_name: str
    affected: list[ImpactUnit] = []
    total_affected: int = 0


class DocumentRequest(BaseModel):
    code: str
    unit_name: str = ""


class DocumentResponse(BaseModel):
    documentation: str


class TranslateRequest(BaseModel):
    code: str
    file_path: str
    unit_name: str = ""


class TranslateResponse(BaseModel):
    translation: str


class GlossaryUnit(BaseModel):
    unit_name: str
    unit_type: str = ""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    calls: list[str] = []
    called_by: list[str] = []
    common_blocks: list[str] = []


class GlossaryFile(BaseModel):
    file_path: str
    units: list[GlossaryUnit] = []


class GlossaryResponse(BaseModel):
    files: list[GlossaryFile] = []
    total_units: int = 0
    total_files: int = 0


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


@lru_cache(maxsize=128)
def _cached_ask(question: str, top_k: int) -> tuple:
    """Cache full RAG pipeline results."""
    results = retrieve(question, top_k=top_k)
    if not results:
        return "No relevant code found. The index may be empty.", []
    context = assemble_context(results)
    answer = generate_answer(question, context)
    chunks = _build_chunks(results)
    return answer, chunks


@app.post("/api/ask", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """Answer a natural language question about the NASTRAN-95 codebase."""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        answer, chunks = _cached_ask(request.question.strip(), request.top_k)
        return QueryResponse(answer=answer, chunks=chunks)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")


@app.post("/api/ask/stream")
async def ask_question_stream(request: QueryRequest):
    """Stream an answer with SSE. Sends chunks metadata first, then answer tokens."""
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        results = retrieve(request.question, top_k=request.top_k)
        chunks = _build_chunks(results)
        context = assemble_context(results) if results else ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")

    def event_stream():
        # First event: send the retrieved chunks
        chunks_data = [c.model_dump() for c in chunks]
        yield f"event: chunks\ndata: {json.dumps(chunks_data)}\n\n"

        if not results:
            yield f"event: token\ndata: {json.dumps({'t': 'No relevant code found.'})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # Stream answer tokens
        for token in generate_answer_stream(request.question, context):
            yield f"event: token\ndata: {json.dumps({'t': token})}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/explain")
async def explain_code(request: ExplainRequest):
    """Generate a plain-English explanation of code using LLM."""
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    try:
        settings = get_settings()
        client = _get_openai_client()

        # Build the prompt
        prompt = f"""Explain what this FORTRAN code does in 2-3 sentences. Be concise and focus on the main purpose.

File: {request.file_path}"""
        if request.function_name:
            prompt += f"\nFunction: {request.function_name}"
        prompt += f"""

Code:
{request.code}

Explanation:"""

        response = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        explanation = response.choices[0].message.content or ""
        return {"explanation": explanation.strip()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation failed: {e}")


@app.get("/api/dependencies/{unit_name}", response_model=DependencyResponse)
async def get_dependencies(unit_name: str):
    """Get call graph dependencies and shared state for a program unit."""
    try:
        graph = load_call_graph()
        calls = get_callees(unit_name, graph)
        called_by = get_callers(unit_name, graph)
        common = find_shared_state(unit_name)

        node = graph.get(unit_name, {})
        return DependencyResponse(
            unit_name=unit_name,
            calls=calls,
            called_by=called_by,
            common_blocks=common,
            file=node.get("file", ""),
            line=node.get("line", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dependency lookup failed: {e}")


@app.get("/api/impact/{unit_name}", response_model=ImpactResponse)
async def get_impact(unit_name: str, depth: int = 3):
    """BFS over called_by edges to find all units affected by changes to unit_name."""
    try:
        graph = load_call_graph()
        visited = {}
        queue = [(unit_name, 0)]

        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited[current] = d
            for caller in get_callers(current, graph):
                if caller not in visited:
                    queue.append((caller, d + 1))

        affected = []
        for name, d in visited.items():
            if name == unit_name:
                continue
            node = graph.get(name, {})
            affected.append(ImpactUnit(
                name=name,
                file=node.get("file", ""),
                line=node.get("line", 0),
                depth=d,
            ))
        affected.sort(key=lambda u: (u.depth, u.name))

        return ImpactResponse(
            unit_name=unit_name,
            affected=affected,
            total_affected=len(affected),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impact analysis failed: {e}")


@app.post("/api/document", response_model=DocumentResponse)
async def document_code(request: DocumentRequest):
    """Generate documentation for a code snippet using LLM."""
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    try:
        settings = get_settings()
        client = _get_openai_client()

        prompt = f"""Generate concise technical documentation for this FORTRAN subroutine/function.
Include: Purpose, Parameters (if any), Key Operations, and Return Value (if applicable).
Use markdown formatting.

Unit name: {request.unit_name or 'Unknown'}

Code:
{request.code}

Documentation:"""

        response = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        documentation = response.choices[0].message.content or ""
        return DocumentResponse(documentation=documentation.strip())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Documentation generation failed: {e}")


@app.post("/api/translate", response_model=TranslateResponse)
async def translate_code(request: TranslateRequest):
    """Translate FORTRAN code to idiomatic Python equivalent."""
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    try:
        settings = get_settings()
        client = _get_openai_client()

        prompt = f"""Translate this FORTRAN code into idiomatic Python. Provide:
1. The Python equivalent using modern libraries (NumPy/SciPy where appropriate)
2. Brief inline comments noting key differences from the FORTRAN original

Keep the translation concise and practical. Use markdown with a python code block.

File: {request.file_path}
Unit: {request.unit_name or 'Unknown'}

FORTRAN code:
{request.code}

Python translation:"""

        response = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        translation = response.choices[0].message.content or ""
        return TranslateResponse(translation=translation.strip())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}")


@lru_cache(maxsize=1)
def _cached_glossary() -> GlossaryResponse:
    """Cache glossary data since it only changes on re-ingest."""
    import chromadb
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chromadb_path)
    collection = client.get_collection(name=settings.collection_name)

    all_data = collection.get(include=["metadatas"])

    graph = load_call_graph()
    cb_index = load_common_blocks()

    # Pre-build reverse index: unit_name -> [block_names]
    unit_to_blocks: dict[str, list[str]] = {}
    for block_name, block_data in cb_index.items():
        for ref in block_data.get("referenced_by", []):
            uname = ref.get("unit", "").upper()
            if uname:
                unit_to_blocks.setdefault(uname, []).append(block_name)

    files_map: dict[str, list[GlossaryUnit]] = {}
    seen: set[tuple[str, str]] = set()
    for meta in all_data["metadatas"]:
        fp = meta.get("file_path", "")
        name = meta.get("unit_name", "")
        if not name:
            continue

        key = (name.upper(), fp)
        if key in seen:
            continue
        seen.add(key)

        name_upper = name.upper()
        node = graph.get(name_upper, {})

        unit_blocks = unit_to_blocks.get(name_upper, [])

        unit = GlossaryUnit(
            unit_name=name,
            unit_type=meta.get("unit_type", ""),
            file_path=fp,
            line_start=meta.get("line_start", 0),
            line_end=meta.get("line_end", 0),
            calls=node.get("calls", []),
            called_by=node.get("called_by", []),
            common_blocks=sorted(unit_blocks),
        )

        if fp not in files_map:
            files_map[fp] = []
        files_map[fp].append(unit)

    files = []
    for fp in sorted(files_map.keys()):
        units = sorted(files_map[fp], key=lambda u: u.line_start)
        files.append(GlossaryFile(file_path=fp, units=units))

    return GlossaryResponse(
        files=files,
        total_units=sum(len(f.units) for f in files),
        total_files=len(files),
    )


@app.get("/api/glossary", response_model=GlossaryResponse)
async def get_glossary():
    """Return all program units grouped by file, enriched with call graph and COMMON block data."""
    try:
        return _cached_glossary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Glossary failed: {e}")



def _build_chunks(results: list[dict]) -> list[ChunkResponse]:
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
    return chunks


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

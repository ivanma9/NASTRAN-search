# Enriched Glossary Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a browsable, searchable glossary of all files and functions in the indexed codebase, enriched with call graph and COMMON block metadata.

**Architecture:** New `GET /api/glossary` endpoint reads all units from ChromaDB metadata + call graph JSON + common blocks JSON, merges them into a file-grouped structure, and returns it. The web UI gets a new glossary panel/tab with a file tree, search/filter, and clickable entries that integrate with existing ask functionality.

**Tech Stack:** FastAPI (existing), ChromaDB (existing), vanilla JS/HTML/CSS (existing web UI pattern)

---

### Task 1: Backend — `GET /api/glossary` endpoint

**Files:**
- Modify: `src/legacylens/api.py`

**Step 1: Add response models to `api.py`**

Add after the existing `TranslateResponse` model (~line 115):

```python
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
```

**Step 2: Add the endpoint**

Add after the `/api/translate` endpoint (~line 383):

```python
@app.get("/api/glossary", response_model=GlossaryResponse)
async def get_glossary():
    """Return all program units grouped by file, enriched with call graph and COMMON block data."""
    try:
        import chromadb
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chromadb_path)
        collection = client.get_collection(name=settings.collection_name)

        # Fetch all metadata (no documents/embeddings needed)
        all_data = collection.get(include=["metadatas"])

        # Load indices
        graph = load_call_graph()
        cb_index = load_common_blocks()

        # Build unit list from ChromaDB metadata
        files_map: dict[str, list[GlossaryUnit]] = {}
        for meta in all_data["metadatas"]:
            fp = meta.get("file_path", "")
            name = meta.get("unit_name", "")
            if not name:
                continue

            name_upper = name.upper()
            node = graph.get(name_upper, {})

            # Find COMMON blocks for this unit from cb_index
            unit_blocks = []
            for block_name, block_data in cb_index.items():
                for ref in block_data.get("referenced_by", []):
                    if ref.get("unit", "").upper() == name_upper:
                        unit_blocks.append(block_name)
                        break

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

        # Sort units within each file by line_start
        files = []
        for fp in sorted(files_map.keys()):
            units = sorted(files_map[fp], key=lambda u: u.line_start)
            files.append(GlossaryFile(file_path=fp, units=units))

        return GlossaryResponse(
            files=files,
            total_units=sum(len(f.units) for f in files),
            total_files=len(files),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Glossary failed: {e}")
```

**Step 3: Verify endpoint works**

Run: `cd /Users/ivanma/Desktop/gauntlet/LegacyLens && uv run uvicorn legacylens.api:app --port 8000 &`
Then: `curl -s http://localhost:8000/api/glossary | python -m json.tool | head -50`
Expected: JSON with `files`, `total_units`, `total_files` fields populated.

**Step 4: Commit**

```bash
git add src/legacylens/api.py
git commit -m "feat: add GET /api/glossary endpoint with enriched unit metadata"
```

---

### Task 2: Web UI — Glossary tab and panel

**Files:**
- Modify: `src/legacylens/web/index.html`

**Step 1: Add a "Glossary" tab button to the header**

In the header area (`.header`), add a tab toggle next to the existing search bar. Add two tab buttons: "Search" (active by default) and "Glossary".

**Step 2: Add glossary panel HTML**

Add a new `#glossary-panel` div as a sibling to the existing `#results-panel`. It should contain:
- A search input for filtering units by name
- A filter dropdown for unit type (all, subroutine, function, program, block_data)
- A stats bar showing total files/units
- A scrollable container with file groups, each expandable to show units

**Step 3: Add glossary CSS**

Style the glossary panel to match the existing NASA theme:
- File headers as collapsible rows with file path (shortened to basename)
- Unit entries showing: type badge, name, line range
- Expandable detail showing calls, called_by, common_blocks
- Color-coded type badges matching existing relevance badge style
- Search highlight on matching text

**Step 4: Add glossary JavaScript**

Implement:
- `loadGlossary()` — fetches `GET /api/glossary`, caches result
- `renderGlossary(data, filter, search)` — renders the file tree with current filters
- `toggleFile(filePath)` — expand/collapse a file's units
- `toggleUnitDetail(unitName)` — expand/collapse unit metadata
- Tab switching between search and glossary views
- Search input with debounced filtering (300ms)
- Unit type dropdown filter
- Click on unit name → populates search bar with "What does [UNIT_NAME] do?" and triggers ask

**Step 5: Test manually in browser**

Run: `uv run uvicorn legacylens.api:app --port 8000`
Open: `http://localhost:8000`
Verify:
- Glossary tab switches view
- Files are listed and expandable
- Units show type badges, line ranges
- Expanding a unit shows calls/called_by/common_blocks
- Search filters units by name
- Type dropdown filters by unit type
- Clicking a unit name triggers a question

**Step 6: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "feat: add enriched glossary panel to web UI with search and filters"
```

---

### Task 3: Performance — Cache glossary response

**Files:**
- Modify: `src/legacylens/api.py`

**Step 1: Add caching to the glossary endpoint**

The glossary data is static (only changes on re-ingest). Wrap the glossary logic in an `lru_cache` similar to the existing `_cached_ask`:

```python
@lru_cache(maxsize=1)
def _cached_glossary() -> dict:
    """Cache glossary data since it only changes on re-ingest."""
    # ... move glossary logic here, return dict for serialization
```

Update the endpoint to call `_cached_glossary()` and construct the response model from the cached dict.

**Step 2: Commit**

```bash
git add src/legacylens/api.py
git commit -m "perf: cache glossary endpoint response"
```

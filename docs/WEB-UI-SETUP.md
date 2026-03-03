# LegacyLens Web UI — Setup & Run

## Quick Start

### Prerequisites
- Python 3.11+
- Virtual environment activated (or uv installed)
- Your CLI backend fully built and working with ingestion complete

### 1. Run the API Backend

**Option A: Using uv (recommended)**
```bash
cd /Users/ivanma/Desktop/gauntlet/LegacyLens
uv run python -m legacylens.api
```

**Option B: Using Python directly**
```bash
cd /Users/ivanma/Desktop/gauntlet/LegacyLens
# Ensure venv is activated
source .venv/bin/activate
python -m legacylens.api
```

**Option C: Run the file directly**
```bash
cd /Users/ivanma/Desktop/gauntlet/LegacyLens
python src/legacylens/api.py
```

The API will start on `http://localhost:8000` with logs showing:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Open the Web UI

The web UI is served automatically by FastAPI:
- **Open in browser:** `http://localhost:8000`

You should see the NASA-themed Mission Control interface.

### 3. Test a Query

1. Type a question: "Where is the main entry point of this program?"
2. Click "LAUNCH QUERY"
3. Wait for results to display

---

## File Structure

```
src/legacylens/
├── __init__.py
├── cli.py              # Existing CLI (unchanged)
├── api.py              # NEW: FastAPI wrapper
├── ingest/
│   └── ...
├── search/
│   └── ...
└── web/
    └── index.html      # NEW: Vue 3 UI (served by FastAPI)
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/ask` | Submit a query, get answer + code snippets |
| `GET` | `/api/status` | Get index metadata (files, chunks, last updated) |
| `GET` | `/api/health` | Health check |
| `GET` | `/` | Serve the Vue web UI |

---

## Expected API Response

```json
{
  "answer": "The main entry point is the NASTRAN subroutine...",
  "chunks": [
    {
      "file_path": "src/nastran.f",
      "line_start": 42,
      "line_end": 85,
      "text": "SUBROUTINE NASTRAN(...)"
    }
  ],
  "related_functions": {
    "calls": ["DREAD", "DCOMP", "DWRITE"],
    "called_by": ["MAIN"],
    "common_blocks": ["/SYSTEM/", "/CARDS/"]
  }
}
```

---

## Customization

### Change the API Port
In `api.py`, line ~180:
```python
uvicorn.run(app, host="0.0.0.0", port=9000)  # Change 8000 to your port
```

### Change Index Status Mock Data
In `api.py`, modify the `get_index_status()` function to read from actual metadata files.

### Styling
All CSS is in `src/legacylens/web/index.html` (lines 10–400). Colors, fonts, animations can be tweaked via the CSS variables at the top:
```css
:root {
    --nasa-blue: #003A70;
    --accent-gold: #FFB81C;
    /* etc */
}
```

---

## Troubleshooting

**Import errors (ModuleNotFoundError):**
- Ensure you're in the project root directory: `/Users/ivanma/Desktop/gauntlet/LegacyLens`
- Verify venv is activated: `source .venv/bin/activate`
- Or use uv: `uv run python src/legacylens/api.py`

**"Index not found" error:**
- Ensure you've run `legacylens ingest ./NASTRAN-95/` first
- Check that `data/chromadb/` exists
- Verify the `CHROMADB_PATH` in `.env` is correct

**API won't start:**
- Check that port 8000 is free: `lsof -i :8000`
- Verify FastAPI is installed: `pip list | grep -i fastapi`
- Check the full error message (should show in terminal)

**Web UI won't load:**
- Check that the API is running: `curl http://localhost:8000/api/health`
- Check browser console for errors (F12 → Console)
- Verify `.env` has valid `VOYAGE_API_KEY` and `OPENAI_API_KEY`

**TypeError: retrieve() takes 1 positional argument:**
- Make sure your `legacylens.search.retriever` module exports a `retrieve()` function
- The API expects: `retrieve(question, top_k=5)` and returns list of result dicts

---

## LLM Response Formatting

The web UI renders LLM answers as **rich markdown**, so instruct GPT-4o-mini to format responses with:

- **Headers** (`## Section Name`) for major topics
- **Bold** (`**important term**`) for key concepts
- **Code blocks** with language hints for FORTRAN:
  ```fortran
  SUBROUTINE EXAMPLE
    IMPLICIT NONE
  END SUBROUTINE
  ```
- **Inline code** (backticks) for variable names and subroutine names
- **Lists** (`-` or `*`) for steps or alternatives
- **Blockquotes** (`>`) for important notes

**Example system prompt for GPT-4o-mini:**
```
You are an expert FORTRAN code analyst. Answer questions about NASTRAN-95 code.

Format your response as markdown:
- Use ## headers for sections
- Use **bold** for important terms
- Use ```fortran code blocks for code examples
- Use `inline code` for subroutine/variable names
- Use lists for multiple items

Be concise but comprehensive.
```

## Next Steps

1. **Integrate with CLI:** Ensure the LLM answer generator (in `legacylens/search/generator.py`) formats responses as markdown
2. **Add metadata persistence:** Save index metadata when ingesting
3. **Error handling:** Add API error messages for edge cases
4. **Deploy:** Use gunicorn/nginx or Docker for production

---

## Tech Stack

- **Backend:** FastAPI (Python)
- **Frontend:** Vue 3 (vanilla, no build step required)
- **Syntax Highlighting:** Highlight.js
- **Fonts:** Google Fonts (IBM Plex, Space Mono)

The web UI requires zero npm/build setup—it's pure HTML/CSS/JS served by FastAPI.

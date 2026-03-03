# LegacyLens Web UI Design

**Date:** 2026-03-03
**Status:** Approved
**Theme:** NASA/Space Race nostalgia with pride
**Scope:** Hybrid approach—CLI first, web UI secondary MVP feature

---

## Overview

A lightweight 2-panel web UI that wraps the existing CLI backend. Lets users ask natural language questions about NASTRAN-95 code and explore results with optional dependency visualization.

---

## Architecture

**Backend:** FastAPI wrapper exposing:
- `POST /api/ask?question="..."` → calls `legacylens ask` internally, returns JSON
- `GET /api/index-status` → returns ingestion metadata

**Frontend:** Lightweight Vue 3 or React SPA calling FastAPI backend

**Integration:** No changes to existing CLI. Web UI is a presentation layer only.

---

## Layout: 2-Column Design

### Left Panel (300px fixed)
**Search Interface**
- Large, prominent search box: "Ask a question about the codebase..."
- Enter to submit
- Loading spinner during query
- Search history (last 10 questions, clickable)

**Index Status**
- Files indexed: X
- Chunks created: Y
- Last indexed: Z
- Reindex button

**Options**
- Toggle: "Show dependencies" (default: OFF)
- Future: Model/settings dropdown

### Right Panel (flexible)
**Question Echo**
- Displays user's question in light box

**LLM Answer**
- Prose from GPT-4o-mini
- Embedded, syntax-highlighted code snippets
- Each snippet includes:
  - File path (clickable)
  - Line range (e.g., lines 127–145)
  - FORTRAN syntax highlighting

**Related Functions (Collapsible, if "Show dependencies" ON)**
- Calls: Functions this code calls
- Called by: Functions that call this code
- Common blocks: COMMON blocks referenced
- Each item is a clickable link

**Error State**
- Friendly error messages for missing index, timeouts, malformed queries

---

## Interaction Patterns

| Action | Behavior |
|--------|----------|
| Click previous question | Auto-fill search box + re-run |
| Click file path | Open file modal/viewer or copy to clipboard |
| Click line range | Highlight those lines |
| Toggle "Show dependencies" | Expand/collapse Related Functions section |
| Keyboard: Cmd/Ctrl+K | Focus search box |
| Keyboard: Escape | Clear search |

---

## Responsive Design

- **Desktop (1200px+):** 2-column layout as designed
- **Tablet (768-1199px):** Left panel → hamburger menu, right panel full width
- **Mobile:** Vertical stack (search, then results)

---

## Tech Stack

- **Frontend:** Vue 3 or React (lightweight)
- **Backend:** FastAPI (Python)
- **HTTP Client:** Fetch API
- **Syntax Highlighting:** Prism.js or highlight.js
- **Storage:** localStorage for search history + preferences

---

## Acceptance Criteria

- [ ] Search box submits queries to `/api/ask` endpoint
- [ ] LLM answer displays with embedded code snippets
- [ ] File paths are clickable
- [ ] "Show dependencies" toggle works (shows/hides Related Functions)
- [ ] Search history persists and is clickable
- [ ] Responsive on desktop, tablet, mobile
- [ ] Error states display friendly messages
- [ ] Index status card shows current metadata
- [ ] Visual design mimics NASA/space race nostalgia

---

## Future Enhancements (Post-MVP)

- Hybrid search (BM25 + vector)
- Re-ranking
- Code viewer modal (see full file, navigate with keyboard)
- Query analytics
- Export results as PDF
- Multi-model support
- Conversation history persistence


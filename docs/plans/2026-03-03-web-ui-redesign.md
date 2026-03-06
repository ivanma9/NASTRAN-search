# Web UI Redesign — LegacyLens

## Problem
Users search for NASTRAN code documentation. Current UI has poor answer readability, no code copy functionality, and a sidebar that wastes space.

## User Workflow
1. Read AI answer to understand the concept
2. Jump to source code snippets to copy/reference lines
3. Search again with follow-up queries

## Design

### Layout
- **Top search bar**: full-width, always visible, replaces sidebar
- **Query history**: dropdown on search input focus
- **Index status**: small indicator near search bar
- **Full-width results**: answer + code snippets use entire content area
- **Landing page**: sample queries as clickable cards
- **Remove**: left sidebar, "Mission Parameters" echo box

### Answer Section
- White card with subtle shadow, clear container
- Lightweight markdown: paragraphs, bold, inline code, lists
- 1.05rem font, 1.8 line-height for readability
- Visual separator before code snippets section

### Code Snippets
- Collapsible cards: file path + first 5 lines visible, click to expand
- Copy button in header (clipboard icon → checkmark on success)
- Line numbers in left gutter matching source file line numbers
- Lighter code background (#4a5568) for FORTRAN readability
- File path prominent, relevance badge smaller/secondary
- Low-relevance snippets collapsed by default

### Keep
- NASA theming (colors, fonts, identity)
- Loading facts during search
- Relevance badges (high/medium/low)
- Show Dependencies toggle

### Remove
- Left sidebar
- "Mission Parameters" query echo box

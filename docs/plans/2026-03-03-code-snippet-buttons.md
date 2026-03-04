# Code Snippet Interactive Buttons Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add "Explain" and "Callers" interactive buttons to code snippet display, allowing users to generate explanations and navigate to dependencies.

**Architecture:** Frontend Vue.js component additions handle button clicks and display state. "Explain" button calls new `/api/explain` backend endpoint which uses LLM to generate explanation. "Callers" button scrolls to existing dependency section. All changes are additive with no breaking changes.

**Tech Stack:** Vue 3, FastAPI, OpenAI API

---

## Task 1: Add Vue Data Properties for Explain State

**Files:**
- Modify: `src/legacylens/web/index.html:898-945` (data section)

**Step 1: View current data structure**

Open the file and locate the `data()` function around line 898.

**Step 2: Add explain state properties**

In the `data()` return object, add these properties after `nasaFacts`:

```javascript
explainLoading: {},      // Track loading state per snippet index
explanations: {},        // Store generated explanations per snippet index
```

Example insertion point (after line 944, before closing `}`):
```javascript
                    ]
                };
            },
            mounted() {
```

Should become:
```javascript
                    ]
                };
                this.explainLoading = {};
                this.explanations = {};
            },
            mounted() {
```

**Step 3: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "feat: add explain/callers state properties to Vue data"
```

---

## Task 2: Add Explain and Callers Buttons to Snippet Header

**Files:**
- Modify: `src/legacylens/web/index.html:850-856` (snippet header)

**Step 1: Locate snippet header**

Find line 850 with `<div class="snippet-header">`. The header currently has:
```html
<span class="file-path">📁 {{ chunk.file_path }}</span>
<span class="relevance-badge">...</span>
<span class="line-range">Lines {{ chunk.line_start }}–{{ chunk.line_end }}</span>
```

**Step 2: Add buttons after line-range**

Replace the snippet header with:

```html
                            <div class="snippet-header">
                                <span class="file-path">📁 {{ chunk.file_path }}</span>
                                <span :class="['relevance-badge', 'relevance-' + getRelevance(chunk.score).level]">
                                    {{ getRelevance(chunk.score).label }} ({{ chunk.score.toFixed(3) }})
                                </span>
                                <span class="line-range">Lines {{ chunk.line_start }}–{{ chunk.line_end }}</span>
                                <div class="snippet-actions">
                                    <button class="action-btn explain-btn"
                                            @click="explainSnippet(idx)"
                                            :disabled="explainLoading[idx]">
                                        {{ explainLoading[idx] ? '⏳ Explaining...' : '💡 Explain' }}
                                    </button>
                                    <button class="action-btn callers-btn" @click="scrollToCallers">
                                        👥 Callers
                                    </button>
                                </div>
                            </div>
```

**Step 3: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "feat: add explain and callers buttons to snippet header"
```

---

## Task 3: Add CSS Styling for Buttons and Explanation Box

**Files:**
- Modify: `src/legacylens/web/index.html:563-600` (after `.code-snippet` styles)

**Step 1: Locate insertion point**

Find the `.code-snippet` CSS block (around line 475-489). After the closing `}` for `.code-snippet:hover`, add new styles.

**Step 2: Add button and explanation styles**

Insert after line 489:

```css
        .snippet-actions {
            display: flex;
            gap: 0.75rem;
            margin-left: auto;
        }

        .action-btn {
            background: transparent;
            border: 2px solid var(--accent-gold);
            color: var(--mission-white);
            padding: 0.4rem 0.8rem;
            border-radius: 4px;
            font-family: "Space Mono", monospace;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }

        .action-btn:hover:not(:disabled) {
            background: var(--accent-gold);
            color: var(--nasa-blue);
            box-shadow: 0 0 12px rgba(255, 184, 28, 0.3);
        }

        .action-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .explanation-box {
            background: rgba(0, 58, 112, 0.15);
            border-left: 4px solid var(--accent-gold);
            border-radius: 4px;
            padding: 1rem;
            margin: 1rem 0;
            color: var(--text-dark);
            font-size: 0.95rem;
            line-height: 1.6;
        }

        .explanation-box.loading {
            color: var(--text-light);
            font-style: italic;
        }

        .explanation-box.error {
            background: rgba(211, 47, 47, 0.1);
            border-left-color: var(--nasa-red);
            color: var(--nasa-red);
        }
```

**Step 3: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "style: add button and explanation box styling"
```

---

## Task 4: Add Explanation HTML Display Below Code

**Files:**
- Modify: `src/legacylens/web/index.html:860-861` (after code block)

**Step 1: Locate code snippet block**

Find line 860 with `<pre><code...>`. After the closing `</pre>` tag, add:

```html
                            <div v-if="explanations[idx]" class="explanation-box">
                                <strong>💡 Explanation:</strong> {{ explanations[idx] }}
                            </div>
                            <div v-if="explainLoading[idx] && !explanations[idx]" class="explanation-box loading">
                                ⏳ Generating explanation...
                            </div>
```

Insert after line 860 (after `</pre>`):

```html
                            <pre><code class="language-fortran">{{ chunk.text }}</code></pre>
                            <div v-if="explanations[idx]" class="explanation-box">
                                <strong>💡 Explanation:</strong> {{ explanations[idx] }}
                            </div>
                            <div v-if="explainLoading[idx] && !explanations[idx]" class="explanation-box loading">
                                ⏳ Generating explanation...
                            </div>
```

**Step 2: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "feat: add explanation display HTML below code snippets"
```

---

## Task 5: Implement explainSnippet Method

**Files:**
- Modify: `src/legacylens/web/index.html:1138-1150` (methods section)

**Step 1: Locate methods section**

Find the `methods: {` object around line 1138.

**Step 2: Add explainSnippet method**

Add this new method before `selectFromHistory`:

```javascript
                async explainSnippet(index) {
                    const chunk = this.results.chunks[index];
                    if (!chunk) return;

                    this.explainLoading[index] = true;
                    this.$forceUpdate(); // Force Vue to update UI

                    try {
                        const response = await fetch(`${this.apiBase}/explain`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                code: chunk.text,
                                file_path: chunk.file_path,
                                function_name: chunk.text.split('\n')[0] // First line often has function name
                            })
                        });

                        if (!response.ok) {
                            throw new Error(`API error: ${response.statusText}`);
                        }

                        const data = await response.json();
                        this.explanations[index] = data.explanation;
                    } catch (err) {
                        this.explanations[index] = `Error: ${err.message || 'Failed to generate explanation'}`;
                    } finally {
                        this.explainLoading[index] = false;
                        this.$forceUpdate();
                    }
                },

                scrollToCallers() {
                    // Implementation in next task
                },
```

**Step 3: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "feat: implement explainSnippet method for LLM explanations"
```

---

## Task 6: Implement scrollToCallers Method

**Files:**
- Modify: `src/legacylens/web/index.html:1138-1150` (methods section)

**Step 1: Find the scrollToCallers placeholder**

From previous task, there should be an empty `scrollToCallers()` method.

**Step 2: Implement scrollToCallers**

Replace:
```javascript
                scrollToCallers() {
                    // Implementation in next task
                },
```

With:
```javascript
                scrollToCallers() {
                    // Find the related-functions section
                    const section = document.querySelector('.related-functions');
                    if (section) {
                        // Scroll to the section
                        section.scrollIntoView({ behavior: 'smooth', block: 'start' });

                        // Find and highlight the "Called By" subsection
                        const calledByDiv = section.querySelector('.dependency-group:nth-child(2)');
                        if (calledByDiv) {
                            calledByDiv.style.backgroundColor = 'rgba(255, 184, 28, 0.1)';
                            setTimeout(() => {
                                calledByDiv.style.backgroundColor = '';
                            }, 2000);
                        }
                    }
                },
```

**Step 3: Commit**

```bash
git add src/legacylens/web/index.html
git commit -m "feat: implement scrollToCallers to navigate to dependencies"
```

---

## Task 7: Create Backend /api/explain Endpoint

**Files:**
- Modify: `src/legacylens/api.py` (locate the main FastAPI app file)

**Step 1: Find the correct API file**

Locate the FastAPI app initialization. This is likely in `src/legacylens/api.py` or similar.

**Step 2: Add the explain endpoint**

Add this new route before or after your existing endpoints:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

class ExplainRequest(BaseModel):
    code: str
    file_path: str
    function_name: Optional[str] = None

@app.post("/api/explain")
async def explain_code(request: ExplainRequest):
    """Generate a plain-English explanation of code using LLM."""
    try:
        # Use your existing LLM client
        from legacylens.core.rag import get_llm_client

        prompt = f"""Explain what this FORTRAN code does in 2-3 sentences. Be concise and focus on the main purpose.

File: {request.file_path}
Code:
{request.code}

Explanation:"""

        client = get_llm_client()
        response = client.messages.create(
            model="gpt-4o-mini",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )

        explanation = response.content[0].text.strip()
        return {"explanation": explanation}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 3: Verify imports at top of file**

Ensure these imports exist:
```python
from typing import Optional
from pydantic import BaseModel
```

**Step 4: Commit**

```bash
git add src/legacylens/api.py
git commit -m "feat: add /api/explain endpoint for code explanations"
```

---

## Task 8: Manual Testing - Frontend

**Files:**
- Test: `src/legacylens/web/index.html` (manual browser test)

**Step 1: Start the dev server**

```bash
# In your project root
docker build -t legacylens:latest . && docker run -p 8000:8000 --env-file .env legacylens:latest &
```

**Step 2: Open browser**

Navigate to `http://localhost:8000`

**Step 3: Perform a search**

Query: "DCOMP" (or any query that returns results)

**Step 4: Test Explain button**

- Click the "💡 Explain" button on any code snippet
- Verify: Loading state shows "⏳ Explaining..."
- Verify: After 2-3 seconds, explanation appears below code
- Verify: Button shows "💡 Explain" again

**Step 5: Test Callers button**

- Click the "👥 Callers" button
- Verify: Page smoothly scrolls to "Dependency Manifest" section
- Verify: "Called By" subsection highlights with gold background for 2 seconds

**Step 6: Test error handling**

- If explanation fails, verify error message appears

**Step 7: Commit**

```bash
git add -A
git commit -m "test: manual testing of explain and callers buttons"
```

---

## Task 9: Integration Testing - Backend

**Files:**
- Test: Manual curl test

**Step 1: Test endpoint exists**

```bash
curl -X POST http://localhost:8000/api/explain \
  -H "Content-Type: application/json" \
  -d '{"code": "SUBROUTINE TEST\nEND SUBROUTINE", "file_path": "test.f", "function_name": "TEST"}'
```

**Expected response:**
```json
{
  "explanation": "This is a FORTRAN subroutine named TEST that does [something]..."
}
```

**Step 2: Test error handling**

```bash
curl -X POST http://localhost:8000/api/explain \
  -H "Content-Type: application/json" \
  -d '{"code": "", "file_path": ""}'
```

Should return either valid explanation or HTTP 500 with error detail.

**Step 3: Commit**

```bash
git add -A
git commit -m "test: verify /api/explain endpoint functionality"
```

---

## Summary

**Total commits:** 9
**Frontend changes:** 5 commits (data, buttons, styling, HTML, methods)
**Backend changes:** 1 commit (endpoint)
**Testing:** 2 commits (manual tests)

**Key files modified:**
- `src/legacylens/web/index.html` - All frontend changes
- `src/legacylens/api.py` - Backend explain endpoint

**No breaking changes** - All changes are additive.


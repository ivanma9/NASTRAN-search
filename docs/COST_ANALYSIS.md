# LegacyLens — AI Cost Analysis

**Date:** 2026-03-06
**Project:** LegacyLens RAG System for NASTRAN-95

---

## 1. Development & Testing Costs (Actual Spend)

### Embedding Costs (Voyage code-3)

| Metric | Value |
|--------|-------|
| Total chunks indexed | 4,520 |
| Average tokens per chunk | ~705 |
| Total tokens embedded | ~3,185,572 |
| Voyage code-3 price | $0.06 / 1M tokens |
| **Embedding cost** | **$0.19** |

### LLM Costs (GPT-4o-mini)

Estimated development usage (testing queries):

| Metric | Value |
|--------|-------|
| Test queries during dev | ~200 |
| Avg context tokens per query | ~2,000 |
| Avg response tokens | ~300 |
| Total input tokens | ~400,000 |
| Total output tokens | ~60,000 |
| GPT-4o-mini input price | $0.15 / 1M tokens |
| GPT-4o-mini output price | $0.60 / 1M tokens |
| **LLM cost** | **$0.10** |

### Vector Database Costs (ChromaDB)

| Metric | Value |
|--------|-------|
| Storage type | Embedded (local) |
| Index size | ~84 MB |
| Hosting cost | **$0.00** |

### Total Development Spend

| Category | Cost |
|----------|------|
| Embedding API (Voyage) | $0.19 |
| LLM API (GPT-4o-mini) | $0.10 |
| Vector DB (ChromaDB) | $0.00 |
| Railway hosting (deploy) | $0.00 (free tier) |
| **Total** | **$0.29** |

---

## 2. Production Cost Projections

### Assumptions

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Queries per user per day | 5 | Typical developer usage |
| Avg prompt tokens (system + context) | 2,500 | 3 chunks @ ~700 tokens + system prompt |
| Avg response tokens | 300 | Concise code explanations |
| Query embedding tokens | 25 | Short natural language questions |
| New code indexed per month | 0 | Static codebase (NASTRAN-95) |
| Cache hit rate | 30% | LRU cache for repeated queries |

### Pricing Reference (March 2026)

| Service | Price |
|---------|-------|
| Voyage code-3 embedding | $0.06 / 1M tokens |
| GPT-4o-mini input | $0.15 / 1M tokens |
| GPT-4o-mini output | $0.60 / 1M tokens |
| Railway (if upgraded) | $5/month hobby tier |
| ChromaDB | Free (embedded) |

### Monthly Cost Projections

#### 100 Users

```
Monthly queries = 100 × 5 × 30 × 0.7 (after cache) = 10,500 queries

Query embedding:    10,500 × 25 tokens = 262,500 tokens → $0.02
LLM input:          10,500 × 2,500 tokens = 26.25M tokens → $3.94
LLM output:         10,500 × 300 tokens = 3.15M tokens → $1.89
Infrastructure:     Railway free tier → $0.00
```

| Component | Cost |
|-----------|------|
| Query embeddings | $0.02 |
| LLM input tokens | $3.94 |
| LLM output tokens | $1.89 |
| Infrastructure | $0.00 |
| **Total** | **~$6/month** |

#### 1,000 Users

```
Monthly queries = 1,000 × 5 × 30 × 0.7 = 105,000 queries

Query embedding:    105,000 × 25 = 2.625M tokens → $0.16
LLM input:          105,000 × 2,500 = 262.5M tokens → $39.38
LLM output:         105,000 × 300 = 31.5M tokens → $18.90
Infrastructure:     Railway Pro tier → $20.00
```

| Component | Cost |
|-----------|------|
| Query embeddings | $0.16 |
| LLM input tokens | $39.38 |
| LLM output tokens | $18.90 |
| Infrastructure | $20.00 |
| **Total** | **~$80/month** |

#### 10,000 Users

```
Monthly queries = 10,000 × 5 × 30 × 0.7 = 1,050,000 queries

Query embedding:    1.05M × 25 = 26.25M tokens → $1.58
LLM input:          1.05M × 2,500 = 2.625B tokens → $393.75
LLM output:         1.05M × 300 = 315M tokens → $189.00
Infrastructure:     Railway + Redis cache → $50.00
```

| Component | Cost |
|-----------|------|
| Query embeddings | $1.58 |
| LLM input tokens | $393.75 |
| LLM output tokens | $189.00 |
| Infrastructure | $50.00 |
| **Total** | **~$635/month** |

#### 100,000 Users

```
Monthly queries = 100,000 × 5 × 30 × 0.5 (higher cache rate) = 7,500,000 queries

Query embedding:    7.5M × 25 = 187.5M tokens → $11.25
LLM input:          7.5M × 2,500 = 18.75B tokens → $2,812.50
LLM output:         7.5M × 300 = 2.25B tokens → $1,350.00
Infrastructure:     Kubernetes + Redis + monitoring → $300.00
```

| Component | Cost |
|-----------|------|
| Query embeddings | $11.25 |
| LLM input tokens | $2,812.50 |
| LLM output tokens | $1,350.00 |
| Infrastructure | $300.00 |
| **Total** | **~$4,475/month** |

### Summary Table

| Scale | Monthly Cost | Cost per User | Primary Driver |
|-------|-------------|---------------|----------------|
| 100 users | ~$6 | $0.06 | LLM tokens |
| 1,000 users | ~$80 | $0.08 | LLM tokens |
| 10,000 users | ~$635 | $0.06 | LLM tokens |
| 100,000 users | ~$4,475 | $0.04 | LLM tokens (with caching) |

---

## 3. Cost Optimization Opportunities

### High Impact

1. **Query Caching (30-50% savings)**
   - Current: LRU cache with 128 slots
   - Upgrade: Redis with semantic similarity matching
   - Similar questions get cached answers
   - Estimated savings at 10K users: ~$200/month

2. **Model Tiering (40-60% savings)**
   - Simple queries → GPT-4o-mini (current)
   - Complex analysis → Claude Sonnet (on demand)
   - Most queries are simple lookups
   - Estimated savings: ~$150/month at 10K users

3. **Context Compression (20-30% savings)**
   - Current: Send full 3 chunks (~2,500 tokens)
   - Optimization: Summarize chunks before sending
   - Use cheaper model for summarization
   - Estimated savings: ~$100/month at 10K users

### Medium Impact

4. **Embedding Caching**
   - Cache query embeddings for repeated questions
   - Voyage costs are already low (<1% of total)
   - Marginal benefit but easy to implement

5. **Batch Processing**
   - Group similar queries for bulk processing
   - Reduces API call overhead
   - Better for async/background workloads

---

## 4. Cost Breakdown Visualization

```
100 Users:     [====                    ] $6/mo
1,000 Users:   [========                ] $80/mo
10,000 Users:  [================        ] $635/mo
100,000 Users: [========================] $4,475/mo

Cost Distribution (10K users):
├── LLM Input Tokens:  62% ($394)
├── LLM Output Tokens: 30% ($189)
├── Infrastructure:     8% ($50)
└── Embeddings:        <1% ($2)
```

---

## 5. Key Insights

1. **LLM tokens dominate costs** — 92% of variable costs are LLM API calls
2. **Embeddings are cheap** — One-time ingestion cost is negligible (~$0.19 for entire codebase)
3. **Caching is critical** — 30% cache hit rate reduces costs significantly
4. **Output tokens are 4x more expensive** — Keep responses concise (current 300 token limit is good)
5. **Infrastructure is minimal** — ChromaDB embedded means no vector DB hosting costs

---

## References

- [Voyage AI Pricing](https://www.voyageai.com/pricing) — $0.06/1M tokens for code-3
- [OpenAI Pricing](https://openai.com/api/pricing/) — GPT-4o-mini rates
- [Railway Pricing](https://railway.app/pricing) — Free tier, $5/mo hobby

# Journal

## Week 7 — Issue selection

**Issue link:** [https://github.com/ascherj/pathreview/issues/24](https://github.com/ascherj/pathreview/issues/24)

**Issue title:** Hybrid retriever over-weights keyword results when query contains technology names

**Tier:** [ ] Tier 1  [x] Tier 2  [ ] Tier 3

**Problem summary:**
The hybrid retriever blends keyword (sparse) and vector (dense) search scores to rank results, but when a query includes a technology name (e.g. a specific framework or library), the keyword-match component dominates the combined score. This crowds out semantically relevant results that don't happen to contain the exact tech-name token, even when those results are a better match for the user's underlying question. A successful fix would rebalance or normalize the scoring so tech-name queries return a ranking that reflects semantic relevance alongside exact keyword matches, rather than keyword matches overwhelming the blend. This affects the hybrid retriever/scoring logic in the RAG retrieval layer.

**Branch name:** `fix/24-hybrid-retriever-keyword-overweight`

**Setup confirmation:** [x] App runs locally at localhost:5173

**Cohort ledger:** [x] Issue added to cohort ledger

# Journal

## Week 7 — Issue selection

**Issue link:** [https://github.com/ascherj/pathreview/issues/24](https://github.com/ascherj/pathreview/issues/24)

**Issue title:** Hybrid retriever over-weights keyword results when query contains technology names

**Tier:** [ ] Tier 1  [x] Tier 2  [ ] Tier 3

**Problem summary:**
I initially thought this might be a filtering problem because irrelevant chunks from the wrong documents were being attached to the results. However, after looking more closely at the issue, it seems more likely to be a scoring problem. Common technology names such as React or Python can appear frequently across multiple resumes and README files, causing those chunks to receive high BM25 keyword scores even when they are not contextually relevant to the query. Because the hybrid scoring function uses a fixed weighting between BM25 and vector similarity (`vector_weight=0.7`, `keyword_weight=0.3` in [hybrid.py:14](rag/retriever/hybrid.py#L14), combined at [hybrid.py:79-80](rag/retriever/hybrid.py#L79-L80)), these strong keyword matches can rank irrelevant chunks above more semantically relevant ones.

**"Is this right for me?" checklist reasoning:**

*Part 1 — Understanding the issue*
- [x] Can paraphrase the problem in 2-3 sentences (see problem summary above) without re-reading the issue.
- [x] Located the affected area: `rag/retriever/hybrid.py` (score blending) and `rag/retriever/keyword_search.py` (BM25 scoring).
- [x] Can describe before/after: before — a query mentioning "React" surfaces chunks from unrelated resumes just because they contain the word "React"; after — ranking reflects semantic relevance to the query even when a tech name appears in off-topic chunks.

*Part 2 — Tier fit*
- [x] Tier 2 — this touches how keyword search and vector search interact through the shared scoring function, not a single isolated file, but it doesn't require touching the ingestion pipeline or infra.
- [x] I've done Tier 1-equivalent work before (small isolated fixes), so a Tier 2 scoring fix is a reasonable stretch without being a first-contribution risk.

*Part 3 — Codebase readiness*
- [x] Found and read the specific function: `HybridRetriever.retrieve()` in [hybrid.py](rag/retriever/hybrid.py), including the fixed-weight blend at lines 79-80.
- [x] Read enough surrounding context (constructor defaults, `keyword_search.py` BM25 implementation) to sketch a rough plan: likely either normalize BM25 scores before blending, or make weighting adaptive/query-dependent instead of a static constant.
- [ ] Read the relevant test file — no test file currently exists for the hybrid retriever (checked `tests/unit/` and `tests/`, no `hybrid` matches). Will write the test file from scratch rather than extend an existing one; noting this as an open item to revisit before implementation in Week 8.

*Part 4 — Scope and time*
- [x] Checked issue comments and cohort ledger claims count — comfortable with current claim count on this issue.
- [x] Estimated 8-12 hours for a Tier 2 fix (scoring change + normalization/adaptive-weight logic + new tests); fits within the Week 8-9 window alongside other commitments.
- [x] No blockers or "blocked by #X" dependencies noted on the issue.

**Branch name:** `fix/24-hybrid-retriever-keyword-overweight`

**Setup confirmation:** [x] App runs locally at localhost:5173

**Cohort ledger:** [x] Issue added to cohort ledger

## Week 8 — Reproduction & Solution Planning

**Reproduction commit:** [https://github.com/kaiser1x/pathreview/commit/86b9fec](https://github.com/kaiser1x/pathreview/commit/86b9fec)

**Reproduction summary:**
Added [`tests/unit/test_hybrid_retriever.py`](tests/unit/test_hybrid_retriever.py) — no test file existed for
`hybrid.py` before this (flagged as an open item in Week 7). Two passing tests currently document the *buggy*
behavior (they assert the bug is present, so they'll need inverting once a fix lands):

1. `test_keyword_heavy_wrong_doc_chunk_outranks_relevant_chunk` — constructs a wrong-document chunk that
   repeats "React" (high raw BM25 score) alongside a genuinely relevant chunk that is only the *second-best*
   vector match. The wrong-doc chunk outranks the relevant one despite `vector_weight=0.7` vs.
   `keyword_weight=0.3`.
2. `test_keyword_score_normalized_by_batch_max_not_absolute` — isolates the mechanism: `keyword_score` is
   computed as `bm25_score / max(bm25_score in this batch)` ([hybrid.py:58-59](rag/retriever/hybrid.py#L58-L59)),
   so a chunk that never appears in the vector results at all can still land a `keyword_score` near 1.0 purely
   because another chunk sharing the same common tech term set the batch max.

**Root cause (confirmed):** batch-relative BM25 normalization inflates keyword scores for common, low-idf
terms (like tech names) regardless of absolute relevance, letting keyword-heavy wrong-document chunks
out-blend a relevant chunk that isn't the single top vector match. Full writeup with code line references in
[PLAN.md](PLAN.md#understand).

**Secondary finding:** `HybridRetriever._get_all_chunks()` fetches all chunks every call but never uses the
result ([hybrid.py:50-51](rag/retriever/hybrid.py#L50-L51)), and `KeywordSearcher` is searched without ever
being `.index()`ed with the current collection's chunks first — likely a second bug (stale/cross-profile
keyword index) noted in [PLAN.md](PLAN.md#plan-implementation-tasks--not-implemented-yet-per-instructions)
task 3 for Week 9 investigation.

**PLAN.md:** [PLAN.md](PLAN.md) — 5 implementation tasks, risks, and edge cases documented.

**Walkthrough video:** [https://www.loom.com/share/921b7772fb644f889a96c13c34e5fdb0](https://www.loom.com/share/921b7772fb644f889a96c13c34e5fdb0)

**Blockers / Open questions:**
- `HybridRetriever` isn't wired into any live caller yet (no instantiation site found outside `hybrid.py`
  itself) — need to confirm intended integration point before changing the constructor's public API.
- Repo had no local `.venv`; created one with Python 3.12 (repo requires `>=3.11`, and the pre-existing shared
  `.venv` at `c:\AI201\.venv` was 3.10) and ran `pip install -e ".[dev]"` to get `pytest`/`structlog`/etc.
- Full `tests/unit` run shows 53 pre-existing failures unrelated to this issue (confirmed by running the
  suite with and without the new test file — same 53 failures either way); not investigated further as
  out of scope for #24.

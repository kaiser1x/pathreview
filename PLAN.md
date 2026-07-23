# PLAN.md — Issue #24: Hybrid retriever over-weights keyword results when query contains technology names

## Issue

[https://github.com/ascherj/pathreview/issues/24](https://github.com/ascherj/pathreview/issues/24)

Hybrid retriever blends vector similarity and BM25 keyword scores. Technology
names ("React", "Python", etc.) appear frequently across unrelated resume and
README chunks. When a query contains one of these terms, chunks from the
wrong document can outrank the actually relevant chunk.

## Understand

- **Expected:** ranking reflects semantic relevance to the query even when a
  tech term also appears verbatim in unrelated chunks.
- **Actual:** a chunk from an unrelated document that repeats a common tech
  term can outrank a chunk that is genuinely relevant to the query but isn't
  the single best vector match.
- **Confirmed root cause:** in [`HybridRetriever.retrieve()`](rag/retriever/hybrid.py#L57-L81),
  both `vector_score` and `keyword_score` are normalized by dividing by the
  **max score within the current result batch** ([hybrid.py:58-59](rag/retriever/hybrid.py#L58-L59)):

  ```python
  vector_scores_max = max([r["score"] for r in vector_results], default=1.0)
  keyword_scores_max = max([r.get("bm25_score", 0) for r in keyword_results], default=1.0)
  ```

  This makes each score relative to *that query's own batch*, not to any
  absolute or global scale. A common tech term has low BM25 idf, so several
  chunks that merely repeat it end up with raw BM25 scores clustered near the
  batch max — each gets normalized to a `keyword_score` close to 1.0
  regardless of whether the chunk is actually about the query topic. A chunk
  that is semantically relevant but is only the *second-best* vector match
  (not the max) gets a `vector_score` well below 1.0. Even with
  `vector_weight=0.7` and `keyword_weight=0.3` ([hybrid.py:14](rag/retriever/hybrid.py#L14)),
  a wrong-document chunk with `keyword_score≈1.0` and a modest `vector_score`
  can out-blend a relevant chunk with a modest `vector_score` and a weak
  `keyword_score`. Reproduced in [`tests/unit/test_hybrid_retriever.py`](tests/unit/test_hybrid_retriever.py).

- Secondary code smell noticed while tracing this: `_get_all_chunks()` is
  called on every `retrieve()` ([hybrid.py:50](rag/retriever/hybrid.py#L50)) and its
  result (`all_chunks`) is never used — dead work, not part of the scoring
  bug, but worth flagging.
- `HybridRetriever` is not currently wired into any caller in the app
  (`grep` found no instantiation site outside `hybrid.py` itself/tests) — this
  is scoring-logic-only work; no live traffic is affected by the fix.

## Map

- `rag/retriever/hybrid.py` — `HybridRetriever.retrieve()`: fetches vector
  results, fetches keyword results, normalizes each score set independently,
  blends by fixed weights, filters by `min_score`, sorts, truncates to
  `max_chunks`.
- `rag/retriever/vector_store.py` — `VectorStore.query()` / `get_collection()`:
  supplies raw vector similarity scores.
- `rag/retriever/keyword_search.py` — `KeywordSearcher.search()`: supplies raw
  BM25 scores via `rank_bm25.BM25Okapi`.
- No existing caller wires `HybridRetriever` into the API/service layer today.
- No existing test file for `hybrid.py` before this work (confirmed via
  `tests/unit/` search) — new `tests/unit/test_hybrid_retriever.py` added as
  the reproduction vehicle.

## Plan (implementation tasks — not implemented yet, per instructions)

1. **Replace batch-relative BM25 normalization with a stable/global scale**
   in `rag/retriever/hybrid.py` (e.g. saturating transform like
   `score / (score + k)`, or normalize against the corpus-wide BM25 score
   distribution captured at index time) so that a common tech term with a
   low absolute BM25 signal doesn't get inflated to ~1.0 just for being the
   batch max.
2. **Consider idf-aware down-weighting** in `rag/retriever/keyword_search.py`
   or at blend time — a match on a token that appears in most chunks in the
   collection should contribute less to the keyword score than a rare
   discriminating term.
3. **Fix `_get_all_chunks` dead-code path** in `hybrid.py:50-51` — either use
   `all_chunks` to build/refresh the BM25 index per-collection before calling
   `keyword_searcher.search()` (it currently searches whatever the searcher
   was last `.index()`ed with, which may not match `collection_name` at all —
   this looks like a second, related bug: keyword search may be running
   against the wrong profile's chunks), or remove the unused fetch if indexing
   is handled elsewhere.
4. **Add regression tests** in `tests/unit/test_hybrid_retriever.py` (already
   started) covering: tech-term-stuffed wrong-doc chunk no longer outranks a
   relevant chunk; keyword score no longer saturates near 1.0 for common
   terms; per-collection keyword index actually matches `collection_name`.
5. **Re-validate weighting defaults** (`vector_weight=0.7`,
   `keyword_weight=0.3`) once normalization is fixed — confirm they still
   produce sane blended rankings on a larger synthetic corpus, since the
   current defaults were tuned against a normalization scheme that's changing.

## Inputs & Outputs

- **Inputs:** `query: str`, `profile_id: str`, `query_embedding: list[float]`,
  `max_chunks: int`, `min_score: float`.
- **Outputs:** `list[dict]`, each with `id`, `text`, `metadata`, `score`,
  `vector_score`, `keyword_score`, sorted descending by blended `score`,
  truncated to `max_chunks`, filtered by `min_score`.

## Risks & Unknowns

- **Risk:** changing normalization shifts absolute score values used
  downstream by `min_score` filtering — callers that hardcode `min_score=0.3`
  may need retuning once the scale changes.
- **Risk:** `KeywordSearcher` is a single stateful instance (`self.bm25`,
  `self.chunks`) indexed via `.index()`; `HybridRetriever` never calls
  `.index()` with the collection's chunks before `.search()` (task 3 above).
  If this is a real bug rather than an out-of-band setup assumption, fixing
  normalization alone won't fix cross-profile keyword leakage.
- **Unknown:** no caller currently wires `HybridRetriever` into the app —
  unclear if this is in-progress/unreleased functionality or on a
  not-yet-merged branch. Need to confirm intended integration point before
  altering the public constructor signature (e.g. adding idf-aware params).
- **Unknown:** whether a synthetic/global BM25 idf table needs to be built at
  ingestion time (per-profile corpus) or can be computed lazily inside
  `retrieve()` — affects task 1/2 design and possibly `KeywordSearcher`'s
  public API.

## Edge Cases

- Query containing only a tech-name token with no other content (e.g. just
  `"React"`) — every chunk mentioning it becomes a keyword match; normalization
  fix must not collapse all keyword scores to near-zero either.
- Very small corpora (few chunks) where BM25 idf is inherently unstable —
  already partially covered by `test_keyword_search.py`'s small-corpus tests.
- Chunk present in keyword results but absent from vector results (or vice
  versa) — existing code already handles via `vector_map`/`keyword_map`
  membership checks ([hybrid.py:69-76](rag/retriever/hybrid.py#L69-L76)); any
  fix must preserve this.
- `vector_results` or `keyword_results` empty — `max(..., default=1.0)`
  guards divide-by-zero today ([hybrid.py:58-59](rag/retriever/hybrid.py#L58-L59));
  fix must keep this safe.
- Multiple wrong-document chunks all containing the same tech term (not just
  one) — the reproduction test's core scenario; fix should hold up with N>1
  competing wrong-doc chunks, not just N=1.

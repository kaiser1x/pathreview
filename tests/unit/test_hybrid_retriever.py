"""Tests for hybrid.py — reproduction of issue #24.

Issue: Hybrid retriever over-weights keyword results when query contains
technology names (e.g. "React", "Python"). Root cause: both vector_score and
keyword_score are normalized against the *max score in the current result
batch* (hybrid.py:58-59), not against a stable reference. When a tech term is
common (low BM25 idf), several chunks from unrelated documents each get a
BM25 score close to the batch max, so they all get keyword_score ~= 1.0. Any
one of those wrong-document chunks can then outrank a correctly relevant
chunk that simply isn't the single top vector match, even though
vector_weight (0.7) is more than double keyword_weight (0.3).
"""

import pytest
from unittest.mock import Mock

from rag.retriever.hybrid import HybridRetriever


@pytest.mark.unit
class TestHybridRetrieverKeywordOverweight:
    """Reproduction tests for issue #24."""

    def _make_retriever(self, vector_results, keyword_results):
        vector_store = Mock()
        vector_store.query.return_value = vector_results

        collection = Mock()
        collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}
        vector_store.get_collection.return_value = collection

        keyword_searcher = Mock()
        keyword_searcher.search.return_value = keyword_results

        return HybridRetriever(vector_store, keyword_searcher)

    def test_keyword_heavy_wrong_doc_chunk_outranks_relevant_chunk(self):
        """Reproduces #24: a wrong-document chunk stuffed with a tech name
        outranks a genuinely relevant chunk that wasn't the top vector match.
        """
        # Correct-document chunk: best-ish but not top vector match, weak
        # keyword overlap (paraphrased, no verbatim "React").
        # Wrong-document chunk: contains "React" repeatedly (common tech
        # term across resumes/READMEs), so BM25 score sits near the batch
        # max even though it is semantically irrelevant to the query.
        vector_results = [
            {"id": "best_vector_other_chunk", "score": 0.95, "text": "unrelated top vector chunk"},
            {"id": "relevant_chunk", "score": 0.55, "text": "built UI components with a component-based JS library"},
            {"id": "wrong_doc_react_stuffed", "score": 0.30, "text": "React React React React frontend developer"},
        ]
        keyword_results = [
            {"id": "wrong_doc_react_stuffed", "bm25_score": 9.8, "text": "React React React React frontend developer"},
            {"id": "relevant_chunk", "bm25_score": 1.2, "text": "built UI components with a component-based JS library"},
        ]

        retriever = self._make_retriever(vector_results, keyword_results)
        results = retriever.retrieve(
            query="React", profile_id="p1", query_embedding=[0.1, 0.2], max_chunks=10, min_score=0.0
        )

        ranked_ids = [r["id"] for r in results]
        relevant_rank = ranked_ids.index("relevant_chunk")
        wrong_doc_rank = ranked_ids.index("wrong_doc_react_stuffed")

        # BUG (current behavior): the tech-name-stuffed wrong-document chunk
        # ranks above the actually relevant chunk despite vector_weight=0.7.
        assert wrong_doc_rank < relevant_rank, (
            "expected current buggy behavior: keyword-stuffed wrong-doc chunk "
            f"outranks relevant chunk (ranked ids: {ranked_ids})"
        )

    def test_keyword_score_normalized_by_batch_max_not_absolute(self):
        """Documents the specific mechanism: keyword_score is relative to the
        max BM25 score in the current batch, so a common tech term can push
        multiple unrelated chunks' keyword_score close to 1.0.
        """
        vector_results = [
            {"id": "a", "score": 0.5, "text": "chunk a"},
        ]
        keyword_results = [
            {"id": "a", "bm25_score": 5.0, "text": "chunk a"},
            {"id": "b", "bm25_score": 4.9, "text": "chunk b, different doc, same tech term"},
        ]

        retriever = self._make_retriever(vector_results, keyword_results)
        results = retriever.retrieve(
            query="React", profile_id="p1", query_embedding=[0.1], max_chunks=10, min_score=0.0
        )

        by_id = {r["id"]: r for r in results}
        # "b" never appeared in vector results at all, yet its keyword_score
        # is nearly identical to "a"'s because both are normalized against
        # the same batch max (5.0), not against an absolute/global scale.
        assert by_id["b"]["keyword_score"] == pytest.approx(4.9 / 5.0, rel=1e-6)
        assert by_id["a"]["keyword_score"] == pytest.approx(1.0)

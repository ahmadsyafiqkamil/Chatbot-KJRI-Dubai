"""Tests for Phase 2 retrieval pipeline — all external deps mocked."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from chatbot_kjri_dubai.rag.retrieval import Retriever, _normalize_scores

CONN_STRING = "postgresql://postgres:postgres@localhost:5432/rag_kjri"
FAKE_EMBEDDING = [0.1] * 3072
CHUNK_ID_1 = str(uuid.uuid4())
CHUNK_ID_2 = str(uuid.uuid4())
DOC_ID_1 = str(uuid.uuid4())


@pytest.fixture()
def mock_psycopg2():
    with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect") as mock_connect:
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value.__enter__ = lambda s: mock_conn
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_connect, mock_conn, mock_cursor


@pytest.fixture()
def mock_chroma():
    with patch("chatbot_kjri_dubai.rag.retrieval.ChromaDBClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def mock_embed():
    with patch(
        "chatbot_kjri_dubai.rag.retrieval.embed_text",
        return_value=FAKE_EMBEDDING,
    ) as m:
        yield m


class TestKeywordSearch:
    def test_returns_list_of_dicts(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (CHUNK_ID_1, "paspor hilang dokumen", DOC_ID_1, 0.5),
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("paspor hilang")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["chunk_id"] == CHUNK_ID_1
        assert results[0]["chunk_text"] == "paspor hilang dokumen"
        assert results[0]["document_id"] == DOC_ID_1
        assert isinstance(results[0]["score"], float)

    def test_uses_plainto_tsquery_in_sql(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = []
        retriever = Retriever(CONN_STRING)
        retriever.keyword_search("paspor")
        sql_called = str(mock_cursor.execute.call_args)
        assert "plainto_tsquery" in sql_called

    def test_empty_db_returns_empty_list(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("paspor")
        assert results == []

    def test_multiple_results_returned(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (CHUNK_ID_1, "text satu", DOC_ID_1, 0.8),
            (CHUNK_ID_2, "text dua", DOC_ID_1, 0.4),
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("query")
        assert len(results) == 2


class TestSemanticSearch:
    def test_returns_list_of_dicts(self, mock_chroma, mock_embed):
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_1,
                "content": "layanan paspor",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.2,
            },
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.semantic_search("paspor hilang")
        assert len(results) == 1
        assert results[0]["chunk_id"] == CHUNK_ID_1
        assert results[0]["chunk_text"] == "layanan paspor"
        assert results[0]["document_id"] == DOC_ID_1
        assert results[0]["score"] == pytest.approx(0.8)

    def test_calls_embed_text_with_query(self, mock_chroma, mock_embed):
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        retriever.semantic_search("paspor")
        mock_embed.assert_called_once_with("paspor", api_key=retriever._api_key)

    def test_empty_chromadb_returns_empty_list(self, mock_chroma, mock_embed):
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.semantic_search("paspor")
        assert results == []

    def test_distance_converted_to_similarity(self, mock_chroma, mock_embed):
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_1,
                "content": "teks",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.0,  # identical → score=1.0
            },
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.semantic_search("teks")
        assert results[0]["score"] == pytest.approx(1.0)


class TestHybridRetrieve:
    def test_deduplicates_same_chunk_id(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (CHUNK_ID_1, "paspor text", DOC_ID_1, 0.8),
        ]
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_1,
                "content": "paspor text",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.1,
            }
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("paspor")
        chunk_ids = [r["chunk_id"] for r in results]
        assert chunk_ids.count(CHUNK_ID_1) == 1

    def test_score_fusion_applies_alpha(self, mock_psycopg2, mock_chroma, mock_embed):
        # chunk_1 keyword-only, chunk_2 semantic-only
        # After normalization both score=1.0 in their stage
        # kw-only:  alpha*1 + (1-alpha)*0 = 0.4
        # sem-only: alpha*0 + (1-alpha)*1 = 0.6
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (CHUNK_ID_1, "text kw", DOC_ID_1, 0.9),
        ]
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_2,
                "content": "text sem",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.1,
            }
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("query", alpha=0.4)
        kw_result = next(r for r in results if r["chunk_id"] == CHUNK_ID_1)
        sem_result = next(r for r in results if r["chunk_id"] == CHUNK_ID_2)
        assert kw_result["score"] == pytest.approx(0.4)
        assert sem_result["score"] == pytest.approx(0.6)
        assert sem_result["score"] > kw_result["score"]

    def test_empty_results(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = []
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("query")
        assert results == []

    def test_top_k_limits_results(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (str(uuid.uuid4()), f"text {i}", DOC_ID_1, float(i + 1))
            for i in range(5)
        ]
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("query", top_k=3)
        assert len(results) <= 3

    def test_result_has_required_keys(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [(CHUNK_ID_1, "text", DOC_ID_1, 0.5)]
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("query")
        assert len(results) == 1
        assert set(results[0].keys()) == {"chunk_id", "chunk_text", "document_id", "score"}


class TestNormalizeScores:
    def test_empty_input(self):
        assert _normalize_scores([]) == []

    def test_single_item_positive_score(self):
        results = [{"chunk_id": "a", "chunk_text": "t", "document_id": "d", "score": 5.0}]
        normed = _normalize_scores(results)
        assert normed[0]["score"] == pytest.approx(1.0)

    def test_single_item_zero_score(self):
        results = [{"chunk_id": "a", "chunk_text": "t", "document_id": "d", "score": 0.0}]
        normed = _normalize_scores(results)
        assert normed[0]["score"] == pytest.approx(0.0)

    def test_different_scores_min_is_zero(self):
        results = [
            {"chunk_id": "a", "chunk_text": "t", "document_id": "d", "score": 2.0},
            {"chunk_id": "b", "chunk_text": "t", "document_id": "d", "score": 4.0},
        ]
        normed = _normalize_scores(results)
        scores = [r["score"] for r in normed]
        assert min(scores) == pytest.approx(0.0)
        assert max(scores) == pytest.approx(1.0)

    def test_does_not_mutate_original(self):
        original = [{"chunk_id": "a", "chunk_text": "t", "document_id": "d", "score": 3.0}]
        _normalize_scores(original)
        assert original[0]["score"] == 3.0

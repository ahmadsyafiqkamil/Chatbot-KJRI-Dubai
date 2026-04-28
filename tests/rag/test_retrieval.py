"""Tests for Phase 2 retrieval pipeline — all external deps mocked."""

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from chatbot_kjri_dubai.rag.retrieval import (
    Retriever,
    _normalize_scores,
    _okapi_bm25_for_doc,
    _reciprocal_rank_fusion,
    _tokenize,
    retriever_from_env,
)

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


def _bm25_response_queue(mock_cursor, responses):
    """Set side_effect untuk urutan execute BM25: COUNT, AVG, DF×n, candidates."""

    state = {"i": 0}

    def on_execute(sql, params=None):
        mock_cursor.fetchall.return_value = None
        mock_cursor.fetchone.return_value = None
        idx = state["i"]
        state["i"] += 1
        if idx >= len(responses):
            return
        entry = responses[idx]
        if "fetchone" in entry:
            mock_cursor.fetchone.return_value = entry["fetchone"]
        if "fetchall" in entry:
            mock_cursor.fetchall.return_value = entry["fetchall"]

    mock_cursor.execute.side_effect = on_execute


class TestTokenizeAndBm25:
    def test_tokenize_lower(self):
        assert _tokenize("Paspor  Hilang!") == ["paspor", "hilang"]

    def test_bm25_positive_when_term_matches(self):
        terms = ["paspor"]
        df = {"paspor": 2}
        s = _okapi_bm25_for_doc(
            "syarat paspor baru",
            terms,
            df,
            n_docs=10,
            avg_doc_len=5.0,
        )
        assert s > 0

    def test_bm25_zero_when_term_absent(self):
        terms = ["hilang"]
        df = {"hilang": 1}
        s = _okapi_bm25_for_doc(
            "paspor baru saja",
            terms,
            df,
            n_docs=10,
            avg_doc_len=5.0,
        )
        assert s == 0.0


class TestKeywordSearch:
    def test_returns_list_of_dicts(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (100,)},
            {"fetchone": (50.0,)},
            {"fetchall": [("paspor", 10), ("hilang", 8)]},
            {"fetchall": [(CHUNK_ID_1, "paspor hilang dokumen", DOC_ID_1)]},
        ]
        _bm25_response_queue(mock_cursor, queue)
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("paspor hilang")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["chunk_id"] == CHUNK_ID_1
        assert results[0]["chunk_text"] == "paspor hilang dokumen"
        assert results[0]["document_id"] == DOC_ID_1
        assert isinstance(results[0]["score"], float)
        assert results[0]["score"] >= 0

    def test_sql_uses_plainto_tsquery(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (10,)},
            {"fetchone": (20.0,)},
            {"fetchall": [("paspor", 1)]},
            {"fetchall": []},
        ]
        _bm25_response_queue(mock_cursor, queue)
        retriever = Retriever(CONN_STRING)
        retriever.keyword_search("paspor")
        sql_logged = [str(call.args[0]) for call in mock_cursor.execute.call_args_list]
        assert any("plainto_tsquery" in s for s in sql_logged)

    def test_empty_db_returns_empty_list(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        queue = [{"fetchone": (0,)}]
        _bm25_response_queue(mock_cursor, queue)
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("paspor")
        assert results == []

    def test_multiple_results_returned(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (100,)},
            {"fetchone": (40.0,)},
            {"fetchall": [("paspor", 5), ("query", 4)]},
            {"fetchall": [
                (CHUNK_ID_1, "text satu paspor", DOC_ID_1),
                (CHUNK_ID_2, "text dua paspor", DOC_ID_1),
            ]},
        ]
        _bm25_response_queue(mock_cursor, queue)
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("paspor query")
        assert len(results) == 2

    def test_non_alphanumeric_query_returns_empty(self, mock_psycopg2, mock_chroma):
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("!!!")
        assert results == []

    def test_legacy_ts_rank_path(self, mock_psycopg2, mock_chroma):
        _, _, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (CHUNK_ID_1, "x", DOC_ID_1, 0.5),
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.keyword_search("q", use_bm25=False)
        assert len(results) == 1
        assert results[0]["score"] == 0.5


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
                "distance": 0.0,
            },
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.semantic_search("teks")
        assert results[0]["score"] == pytest.approx(1.0)


class TestHybridRetrieve:
    def test_deduplicates_same_chunk_id(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (50,)},
            {"fetchone": (30.0,)},
            {"fetchall": [("paspor", 2)]},
            {"fetchall": [(CHUNK_ID_1, "paspor text", DOC_ID_1)]},
        ]
        _bm25_response_queue(mock_cursor, queue)
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
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (20,)},
            {"fetchone": (25.0,)},
            {"fetchall": [("paspor", 1), ("query", 1), ("dua", 1)]},
            {"fetchall": [(CHUNK_ID_1, "text kw paspor", DOC_ID_1)]},
        ]
        _bm25_response_queue(mock_cursor, queue)
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_2,
                "content": "text sem",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.1,
            }
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("paspor query dua", alpha=0.4)
        kw_result = next(r for r in results if r["chunk_id"] == CHUNK_ID_1)
        sem_result = next(r for r in results if r["chunk_id"] == CHUNK_ID_2)
        assert kw_result["score"] == pytest.approx(0.4)
        assert sem_result["score"] == pytest.approx(0.6)
        assert sem_result["score"] > kw_result["score"]

    def test_rrf_fusion(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (20,)},
            {"fetchone": (25.0,)},
            {"fetchall": [("x", 1), ("y", 1)]},
            {"fetchall": [(CHUNK_ID_1, "a", DOC_ID_1)]},
        ]
        _bm25_response_queue(mock_cursor, queue)
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_2,
                "content": "b",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.2,
            }
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("x y", fusion="rrf", rrf_k=60)
        assert len(results) == 2
        assert results[0]["score"] >= results[1]["score"]

    def test_empty_results(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        queue = [{"fetchone": (0,)}]
        _bm25_response_queue(mock_cursor, queue)
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("paspor")
        assert results == []

    def test_top_k_limits_results(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        ids = [(str(uuid.uuid4()), f"text paspor {i}", DOC_ID_1) for i in range(5)]
        queue = [
            {"fetchone": (100,)},
            {"fetchone": (40.0,)},
            {"fetchall": [("paspor", 2), ("satu", 2), ("dua", 2)]},
            {"fetchall": ids},
        ]
        _bm25_response_queue(mock_cursor, queue)
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("paspor satu dua", top_k=3)
        assert len(results) <= 3

    def test_result_has_required_keys(self, mock_psycopg2, mock_chroma, mock_embed):
        _, _, mock_cursor = mock_psycopg2
        queue = [
            {"fetchone": (10,)},
            {"fetchone": (15.0,)},
            {"fetchall": [("paspor", 1), ("tiga", 1)]},
            {"fetchall": [(CHUNK_ID_1, "text paspor", DOC_ID_1)]},
        ]
        _bm25_response_queue(mock_cursor, queue)
        mock_chroma.query_chunks.return_value = []
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("paspor tiga")
        assert len(results) == 1
        assert set(results[0].keys()) == {"chunk_id", "chunk_text", "document_id", "score"}

    def test_semantic_only_when_keyword_empty(self, mock_psycopg2, mock_chroma, mock_embed):
        """Keyword returns empty (n_docs=0), semantic results should still be returned."""
        _, _, mock_cursor = mock_psycopg2
        queue = [{"fetchone": (0,)}]
        _bm25_response_queue(mock_cursor, queue)
        mock_chroma.query_chunks.return_value = [
            {
                "id": CHUNK_ID_1,
                "content": "layanan darurat konsulat",
                "metadata": {"document_id": DOC_ID_1},
                "distance": 0.15,
            }
        ]
        retriever = Retriever(CONN_STRING)
        results = retriever.hybrid_retrieve("darurat")
        assert len(results) == 1
        assert results[0]["chunk_id"] == CHUNK_ID_1
        assert results[0]["score"] > 0


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

    def test_multiple_equal_positive_scores_are_neutral(self):
        results = [
            {"chunk_id": "a", "chunk_text": "t", "document_id": "d", "score": 0.3},
            {"chunk_id": "b", "chunk_text": "t", "document_id": "d", "score": 0.3},
        ]
        normed = _normalize_scores(results)
        assert normed[0]["score"] == pytest.approx(0.5)
        assert normed[1]["score"] == pytest.approx(0.5)

    def test_does_not_mutate_original(self):
        original = [{"chunk_id": "a", "chunk_text": "t", "document_id": "d", "score": 3.0}]
        _normalize_scores(original)
        assert original[0]["score"] == 3.0


class TestRrf:
    def test_merge_and_sort(self):
        kw = [
            {"chunk_id": "a", "chunk_text": "t1", "document_id": "d", "score": 1.0},
            {"chunk_id": "b", "chunk_text": "t2", "document_id": "d", "score": 0.5},
        ]
        sem = [
            {"chunk_id": "b", "chunk_text": "t2", "document_id": "d", "score": 0.9},
            {"chunk_id": "c", "chunk_text": "t3", "document_id": "d", "score": 0.8},
        ]
        out = _reciprocal_rank_fusion(kw, sem, k=60)
        by_id = {r["chunk_id"]: r["score"] for r in out}
        assert "b" in by_id
        assert out[0]["score"] >= out[-1]["score"]


class TestRetrieverFromEnv:
    def test_database_url(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://u:p@db:5432/mydb"},
            clear=False,
        ):
            with patch("chatbot_kjri_dubai.rag.retrieval.ChromaDBClient"):
                r = retriever_from_env()
                assert "db:5432" in r._conn_string

    def test_postgres_components(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "POSTGRES_USER": "a",
                "POSTGRES_PASSWORD": "b",
                "POSTGRES_HOST": "h",
                "POSTGRES_PORT": "5433",
                "POSTGRES_DB": "dbx",
            },
            clear=False,
        ):
            with patch("chatbot_kjri_dubai.rag.retrieval.ChromaDBClient"):
                r = retriever_from_env()
                assert r._conn_string == "postgresql://a:b@h:5433/dbx"

"""
Unit tests for SemanticSearcher and EmbeddingClient — Phase 2 Task 2.

Test strategy:
- All unit tests mock litellm.aembedding and ChromaDBClient to avoid
  requiring a live ChromaDB or Gemini API key.
- The ChromaDBClient.query() signature from Phase 1:
    query(collection, query_embedding: list, n_results: int) -> dict
  The collection is obtained via get_or_create_collection(name).
- EmbeddingError is a custom exception (inherits Exception) raised when
  the embedding API call fails.
- SemanticSearcher.search() is async; tests use pytest-asyncio.

RED phase: EmbeddingClient, SemanticSearcher, EmbeddingError do not yet
exist in retrieval.py — all tests should FAIL on import.
"""

from __future__ import annotations

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# --- imports that drive the RED phase ----------------------------------------
# These will fail until the implementation exists in retrieval.py.
from chatbot_kjri_dubai.rag.retrieval import (
    EmbeddingClient,
    EmbeddingError,
    ResultChunk,
    SemanticSearcher,
)


# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

_FAKE_VECTOR = [0.1] * 768          # 768-dim embedding vector
_FAKE_VECTOR_2 = [0.2] * 768

# ChromaDB cosine-space distances (smaller = more similar; 0 = identical).
# Similarity: 1 - distance
_CHROMA_RESULT_5 = {
    "ids":       [["chunk-001", "chunk-002", "chunk-003", "chunk-004", "chunk-005"]],
    "documents": [["text one", "text two", "text three", "text four", "text five"]],
    "distances": [[0.10, 0.25, 0.40, 0.55, 0.70]],
    "metadatas": [[
        {"document_id": "doc-aaa", "chunk_number": 0, "start_char": 0,   "end_char": 100, "chunk_tokens": 20},
        {"document_id": "doc-aaa", "chunk_number": 1, "start_char": 100, "end_char": 200, "chunk_tokens": 18},
        {"document_id": "doc-bbb", "chunk_number": 0, "start_char": 0,   "end_char": 90,  "chunk_tokens": 17},
        {"document_id": "doc-bbb", "chunk_number": 1, "start_char": 90,  "end_char": 180, "chunk_tokens": 19},
        {"document_id": "doc-ccc", "chunk_number": 0, "start_char": 0,   "end_char": 110, "chunk_tokens": 21},
    ]],
}

_CHROMA_RESULT_EMPTY = {
    "ids":       [[]],
    "documents": [[]],
    "distances": [[]],
    "metadatas": [[]],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_chroma_client():
    """
    A mocked ChromaDBClient whose get_or_create_collection and query methods
    are pre-configured to return _CHROMA_RESULT_5 by default.
    """
    client = MagicMock()
    collection = MagicMock()
    client.get_or_create_collection.return_value = collection
    client.query.return_value = _CHROMA_RESULT_5
    return client, collection


@pytest.fixture
def mock_chroma_client_empty():
    """A mocked ChromaDBClient that returns no results."""
    client = MagicMock()
    collection = MagicMock()
    client.get_or_create_collection.return_value = collection
    client.query.return_value = _CHROMA_RESULT_EMPTY
    return client, collection


@pytest.fixture
def fake_embedding_response():
    """
    Simulate the litellm.EmbeddingResponse object returned by aembedding().
    data[0].embedding is the float vector.
    """
    item = MagicMock()
    item.embedding = _FAKE_VECTOR

    response = MagicMock()
    response.data = [item]
    return response


# ---------------------------------------------------------------------------
# EmbeddingClient tests
# ---------------------------------------------------------------------------

class TestEmbeddingClient:
    """Tests for the EmbeddingClient wrapper around litellm.aembedding."""

    def test_embedding_client_default_model(self):
        """EmbeddingClient initialises with the default Gemini embedding model."""
        client = EmbeddingClient(api_key="test-key")
        assert client.model == "gemini-embedding-001"

    def test_embedding_client_custom_model(self):
        """EmbeddingClient accepts a custom model string."""
        client = EmbeddingClient(api_key="test-key", model="text-embedding-3-small")
        assert client.model == "text-embedding-3-small"

    def test_embedding_client_reads_api_key_from_env(self):
        """EmbeddingClient picks up GEMINI_API_KEY from the environment."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key-123"}):
            client = EmbeddingClient()
        assert client.api_key == "env-key-123"

    def test_embedding_client_explicit_key_overrides_env(self):
        """Explicit api_key parameter takes priority over environment variable."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key"}):
            client = EmbeddingClient(api_key="explicit-key")
        assert client.api_key == "explicit-key"

    @pytest.mark.asyncio
    async def test_embed_text_returns_float_list(self, fake_embedding_response):
        """embed_text() returns a list of floats on success."""
        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding",
                   new=AsyncMock(return_value=fake_embedding_response)):
            client = EmbeddingClient(api_key="test-key")
            vector = await client.embed_text("visa requirements")

        assert isinstance(vector, list)
        assert len(vector) == 768
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.asyncio
    async def test_embed_text_calls_litellm_with_correct_params(
        self, fake_embedding_response
    ):
        """embed_text() passes model, input, and api_key to litellm.aembedding."""
        mock_aembed = AsyncMock(return_value=fake_embedding_response)
        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            client = EmbeddingClient(api_key="my-key", model="gemini-embedding-001")
            await client.embed_text("test query")

        call_kwargs = mock_aembed.call_args.kwargs
        assert call_kwargs.get("model") == "gemini/gemini-embedding-001"
        assert call_kwargs.get("input") == ["test query"]
        assert call_kwargs.get("api_key") == "my-key"

    @pytest.mark.asyncio
    async def test_embed_text_raises_embedding_error_on_api_failure(self):
        """embed_text() wraps any API exception in EmbeddingError."""
        mock_aembed = AsyncMock(side_effect=Exception("rate limit exceeded"))
        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            client = EmbeddingClient(api_key="test-key")
            with pytest.raises(EmbeddingError) as exc_info:
                await client.embed_text("some text")

        assert "rate limit exceeded" in str(exc_info.value).lower() or \
               "embedding" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_embed_text_raises_value_error_on_empty_input(self):
        """embed_text() raises ValueError when given an empty string."""
        client = EmbeddingClient(api_key="test-key")
        with pytest.raises(ValueError, match="empty"):
            await client.embed_text("")

    @pytest.mark.asyncio
    async def test_embed_text_raises_value_error_on_whitespace_input(self):
        """embed_text() raises ValueError when given whitespace-only input."""
        client = EmbeddingClient(api_key="test-key")
        with pytest.raises(ValueError, match="empty"):
            await client.embed_text("   ")


# ---------------------------------------------------------------------------
# SemanticSearcher tests
# ---------------------------------------------------------------------------

class TestSemanticSearcher:
    """Tests for the SemanticSearcher that wraps ChromaDB vector search."""

    # ------------------------------------------------------------------
    # 1. Happy path — basic search returns ResultChunk list
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_basic(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        Happy path: query text is embedded, ChromaDB is queried, and a
        list of ResultChunk objects is returned with correct field mapping.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(
                chroma_client=chroma_mock,
                api_key="test-key",
            )
            results = await searcher.search("visa requirements")

        assert isinstance(results, list)
        assert len(results) > 0
        first = results[0]
        assert isinstance(first, ResultChunk)
        assert first.id == "chunk-001"
        assert first.document_id == "doc-aaa"
        assert first.chunk_text == "text one"
        assert first.chunk_number == 0
        assert first.start_char == 0
        assert first.end_char == 100
        assert first.chunk_tokens == 20

    # ------------------------------------------------------------------
    # 2. similarity_score field populated correctly
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_similarity_score_conversion(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        ChromaDB cosine-space distance d is converted to similarity = 1 - d.
        ResultChunk.relevance_score must equal 1 - distance.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            results = await searcher.search("visa requirements", min_similarity=0.0)

        # distances = [0.10, 0.25, 0.40, 0.55, 0.70]
        expected_scores = [1 - d for d in _CHROMA_RESULT_5["distances"][0]]
        actual_scores = [r.relevance_score for r in results]
        for expected, actual in zip(expected_scores, actual_scores):
            assert abs(actual - expected) < 1e-9, f"Expected {expected}, got {actual}"

    # ------------------------------------------------------------------
    # 3. min_similarity filtering
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_min_similarity_filter(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        Results whose similarity (1 - distance) is below min_similarity
        must be excluded from the returned list.
        Distances: [0.10, 0.25, 0.40, 0.55, 0.70]
        Similarities: [0.90, 0.75, 0.60, 0.45, 0.30]
        With min_similarity=0.60, only first 3 pass.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            results = await searcher.search("visa requirements", min_similarity=0.60)

        assert len(results) == 3
        for r in results:
            assert r.relevance_score >= 0.60

    # ------------------------------------------------------------------
    # 4. max_results respects limit passed to ChromaDB
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_max_results(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        max_results is passed as n_results to ChromaDBClient.query().
        The return count must not exceed max_results.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            await searcher.search("visa requirements", max_results=3, min_similarity=0.0)

        # Verify the client was called with n_results=3
        chroma_mock.query.assert_called_once()
        call_kwargs = chroma_mock.query.call_args
        # n_results can be positional or keyword — check both
        args, kwargs = call_kwargs
        n_results = kwargs.get("n_results") or (args[2] if len(args) > 2 else None)
        assert n_results == 3

    # ------------------------------------------------------------------
    # 5. Empty result set — not an error
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_no_results(
        self, mock_chroma_client_empty, fake_embedding_response
    ):
        """
        When ChromaDB returns no results, search() returns an empty list
        (not an exception).
        """
        chroma_mock, _ = mock_chroma_client_empty
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            results = await searcher.search("query with no match")

        assert results == []

    # ------------------------------------------------------------------
    # 6. Empty query rejected
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_invalid_query_empty(self, mock_chroma_client):
        """search() raises ValueError for an empty query string."""
        chroma_mock, _ = mock_chroma_client

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding",
                   new=AsyncMock()):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(ValueError, match="empty"):
                await searcher.search("")

    # ------------------------------------------------------------------
    # 7. None query rejected
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_invalid_query_none(self, mock_chroma_client):
        """search() raises ValueError when query is None."""
        chroma_mock, _ = mock_chroma_client

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding",
                   new=AsyncMock()):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(ValueError):
                await searcher.search(None)

    # ------------------------------------------------------------------
    # 8. metadata_filter by document_id
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_metadata_filter_document_id(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        metadata_filter={"document_id": "uuid-123"} is forwarded to
        ChromaDBClient.query() as the where parameter.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            await searcher.search(
                "visa requirements",
                metadata_filter={"document_id": "uuid-123"},
                min_similarity=0.0,
            )

        args, kwargs = chroma_mock.query.call_args
        where = kwargs.get("where")
        assert where == {"document_id": "uuid-123"}

    # ------------------------------------------------------------------
    # 9. metadata_filter by source type
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_metadata_filter_source(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        metadata_filter={"source": "pdf"} is forwarded as the where parameter.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            await searcher.search(
                "paspor",
                metadata_filter={"source": "pdf"},
                min_similarity=0.0,
            )

        args, kwargs = chroma_mock.query.call_args
        where = kwargs.get("where")
        assert where == {"source": "pdf"}

    # ------------------------------------------------------------------
    # 10. Invalid metadata_filter keys raise ValueError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_invalid_metadata_filter_type(
        self, mock_chroma_client
    ):
        """search() raises ValueError when metadata_filter is not a dict."""
        chroma_mock, _ = mock_chroma_client

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding",
                   new=AsyncMock()):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(ValueError, match="metadata_filter"):
                await searcher.search("visa", metadata_filter="invalid")

    # ------------------------------------------------------------------
    # 11. ChromaDB connection failure raises ConnectionError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_chroma_connection_failure(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        When ChromaDBClient.query() raises an exception (e.g. server down),
        SemanticSearcher.search() raises ConnectionError.
        """
        chroma_mock, _ = mock_chroma_client
        chroma_mock.query.side_effect = Exception("Connection refused")
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(ConnectionError):
                await searcher.search("visa requirements")

    # ------------------------------------------------------------------
    # 12. get_or_create_collection failure raises ConnectionError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_chroma_collection_failure(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        When get_or_create_collection() fails, ConnectionError is raised.
        """
        chroma_mock, _ = mock_chroma_client
        chroma_mock.get_or_create_collection.side_effect = Exception("server unavailable")
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(ConnectionError):
                await searcher.search("visa requirements")

    # ------------------------------------------------------------------
    # 13. Embedding API failure raises EmbeddingError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_embedding_api_failure(self, mock_chroma_client):
        """
        When litellm.aembedding() raises an exception (e.g. rate limit,
        auth error), SemanticSearcher.search() raises EmbeddingError.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(side_effect=Exception("API quota exceeded"))

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(EmbeddingError):
                await searcher.search("visa requirements")

    # ------------------------------------------------------------------
    # 14. Results are ordered by similarity descending
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_results_ordered_by_similarity(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        Returned ResultChunks are ordered by relevance_score descending
        (highest similarity first).
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            results = await searcher.search("paspor", min_similarity=0.0)

        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True), \
            f"Results not ordered by similarity desc: {scores}"

    # ------------------------------------------------------------------
    # 15. Integration-style test using Phase 1 result shape
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_integration_with_phase1_fixtures(
        self, fake_embedding_response
    ):
        """
        End-to-end test using a fully mocked ChromaDB client configured
        to return a Phase-1-compatible result dict. Verifies that all
        ResultChunk fields align with the Phase 1 DocumentChunk schema.
        """
        chroma_mock = MagicMock()
        collection_mock = MagicMock()
        chroma_mock.get_or_create_collection.return_value = collection_mock

        phase1_result = {
            "ids":       [["c-001"]],
            "documents": [["Paspor harus masih berlaku minimal 6 bulan."]],
            "distances": [[0.15]],
            "metadatas": [[{
                "document_id":  "doc-phase1",
                "chunk_number": 2,
                "start_char":   300,
                "end_char":     370,
                "chunk_tokens": 14,
            }]],
        }
        chroma_mock.query.return_value = phase1_result

        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            results = await searcher.search("paspor berlaku")

        assert len(results) == 1
        chunk = results[0]
        assert chunk.id == "c-001"
        assert chunk.document_id == "doc-phase1"
        assert chunk.chunk_number == 2
        assert chunk.chunk_text == "Paspor harus masih berlaku minimal 6 bulan."
        assert chunk.start_char == 300
        assert chunk.end_char == 370
        assert chunk.chunk_tokens == 14
        assert abs(chunk.relevance_score - (1 - 0.15)) < 1e-9

    # ------------------------------------------------------------------
    # 16. Default min_similarity is 0.5
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_default_min_similarity(
        self, mock_chroma_client, fake_embedding_response
    ):
        """
        With default min_similarity=0.5, chunks with similarity < 0.5
        are filtered out.
        Distances: [0.10, 0.25, 0.40, 0.55, 0.70]
        Similarities: [0.90, 0.75, 0.60, 0.45, 0.30]
        Only the first 3 (similarity >= 0.5) should pass.
        """
        chroma_mock, _ = mock_chroma_client
        mock_aembed = AsyncMock(return_value=fake_embedding_response)

        with patch("chatbot_kjri_dubna.rag.retrieval.litellm.aembedding", new=mock_aembed):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            results = await searcher.search("layanan konsulat")

        assert len(results) == 3
        for r in results:
            assert r.relevance_score >= 0.5

    # ------------------------------------------------------------------
    # 17. whitespace-only query rejected
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_semantic_search_whitespace_query_rejected(
        self, mock_chroma_client
    ):
        """search() raises ValueError when query is whitespace-only."""
        chroma_mock, _ = mock_chroma_client

        with patch("chatbot_kjri_dubai.rag.retrieval.litellm.aembedding",
                   new=AsyncMock()):
            searcher = SemanticSearcher(chroma_client=chroma_mock, api_key="test-key")
            with pytest.raises(ValueError, match="empty"):
                await searcher.search("   ")

    # ------------------------------------------------------------------
    # 18. EmbeddingError is a proper Exception subclass
    # ------------------------------------------------------------------
    def test_embedding_error_is_exception_subclass(self):
        """EmbeddingError must inherit from Exception."""
        assert issubclass(EmbeddingError, Exception)

    def test_embedding_error_carries_message(self):
        """EmbeddingError preserves the error message."""
        err = EmbeddingError("API timed out")
        assert "API timed out" in str(err)

"""Tests for chatbot_kjri_dubai/rag/embeddings.py — Gemini API mocked."""

import os
from unittest.mock import MagicMock, patch

import pytest

from chatbot_kjri_dubai.rag.embeddings import embed_text, EmbeddingError, _client_cache

FAKE_EMBEDDING = [0.1] * 3072
GEMINI_API_KEY = "fake-api-key"


def make_mock_client(embedding=None):
    """Build a mock google.genai.Client that returns a fake embedding."""
    mock_result = MagicMock()
    mock_result.embeddings = [MagicMock(values=embedding or FAKE_EMBEDDING)]

    mock_models = MagicMock()
    mock_models.embed_content.return_value = mock_result

    mock_client = MagicMock()
    mock_client.models = mock_models
    return mock_client


@pytest.fixture(autouse=True)
def clear_client_cache():
    _client_cache.clear()
    yield
    _client_cache.clear()


class TestEmbedText:
    def test_returns_list_of_floats(self):
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=make_mock_client()):
            result = embed_text("Hello world", api_key=GEMINI_API_KEY)
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_returns_3072_dimensions(self):
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=make_mock_client()):
            result = embed_text("Test embedding dimension", api_key=GEMINI_API_KEY)
        assert len(result) == 3072

    def test_consistent_dimension_for_different_inputs(self):
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=make_mock_client()):
            r1 = embed_text("Short text", api_key=GEMINI_API_KEY)
            r2 = embed_text("A much longer text with many more words and sentences.", api_key=GEMINI_API_KEY)
        assert len(r1) == len(r2)

    def test_empty_text_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            embed_text("", api_key=GEMINI_API_KEY)

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            embed_text("   ", api_key=GEMINI_API_KEY)

    def test_missing_api_key_raises_embedding_error(self):
        env_without_key = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(EmbeddingError, match="GEMINI_API_KEY"):
                embed_text("some text", api_key=None)

    def test_api_error_raises_embedding_error(self):
        mock_client = MagicMock()
        mock_client.models.embed_content.side_effect = Exception("API unavailable")
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=mock_client):
            with pytest.raises(EmbeddingError, match="API unavailable"):
                embed_text("some text", api_key=GEMINI_API_KEY)

    def test_calls_correct_model(self):
        mock_client = make_mock_client()
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=mock_client):
            embed_text("test", api_key=GEMINI_API_KEY)
        call_kwargs = mock_client.models.embed_content.call_args
        assert "gemini-embedding-001" in str(call_kwargs)

    def test_uses_retrieval_document_task_type(self):
        mock_client = make_mock_client()
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=mock_client):
            embed_text("test", api_key=GEMINI_API_KEY)
        call_kwargs = str(mock_client.models.embed_content.call_args)
        assert "RETRIEVAL_DOCUMENT" in call_kwargs

    def test_client_is_cached(self):
        mock_client = make_mock_client()
        with patch("chatbot_kjri_dubai.rag.embeddings.genai.Client", return_value=mock_client) as mock_cls:
            embed_text("first call", api_key=GEMINI_API_KEY)
            embed_text("second call", api_key=GEMINI_API_KEY)
        assert mock_cls.call_count == 1, "Client should be instantiated only once per API key"

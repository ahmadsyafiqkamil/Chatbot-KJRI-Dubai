"""Tests for chatbot_kjri_dubai/rag/chromadb_client.py — ChromaDB mocked."""

from unittest.mock import MagicMock, patch

import pytest

from chatbot_kjri_dubai.rag.chromadb_client import ChromaDBClient

FAKE_EMBEDDING = [0.1] * 3072


def make_mock_chroma_client():
    mock_collection = MagicMock()
    mock_collection.name = "test_collection"

    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    return mock_client, mock_collection


class TestChromaDBClient:
    def test_init_creates_http_client(self):
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient") as mock_http:
            mock_http.return_value = MagicMock()
            client = ChromaDBClient(host="localhost", port=8001)
        mock_http.assert_called_once_with(host="localhost", port=8001)

    def test_get_or_create_collection_returns_collection(self):
        mock_chroma, mock_collection = make_mock_chroma_client()
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient", return_value=mock_chroma):
            client = ChromaDBClient()
            coll = client.get_or_create_collection("document_chunks")
        mock_chroma.get_or_create_collection.assert_called_once_with(name="document_chunks")
        assert coll == mock_collection

    def test_upsert_chunks_calls_upsert(self):
        mock_chroma, mock_collection = make_mock_chroma_client()
        chunks = [
            {
                "id": "doc1_chunk_0",
                "content": "Some text content here.",
                "embedding": FAKE_EMBEDDING,
                "metadata": {"document_id": "doc1", "chunk_index": 0},
            }
        ]
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient", return_value=mock_chroma):
            client = ChromaDBClient()
            client.upsert_chunks(mock_collection, chunks)
        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args[1]
        assert call_kwargs["ids"] == ["doc1_chunk_0"]
        assert call_kwargs["documents"] == ["Some text content here."]
        assert len(call_kwargs["embeddings"]) == 1

    def test_upsert_multiple_chunks(self):
        mock_chroma, mock_collection = make_mock_chroma_client()
        chunks = [
            {"id": f"doc1_chunk_{i}", "content": f"Chunk {i}", "embedding": FAKE_EMBEDDING, "metadata": {}}
            for i in range(5)
        ]
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient", return_value=mock_chroma):
            client = ChromaDBClient()
            client.upsert_chunks(mock_collection, chunks)
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["ids"]) == 5

    def test_upsert_empty_list_does_not_call_upsert(self):
        mock_chroma, mock_collection = make_mock_chroma_client()
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient", return_value=mock_chroma):
            client = ChromaDBClient()
            client.upsert_chunks(mock_collection, [])
        mock_collection.upsert.assert_not_called()

    def test_query_chunks_returns_list(self):
        mock_chroma, mock_collection = make_mock_chroma_client()
        mock_collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["text1", "text2"]],
            "metadatas": [[{"doc": "a"}, {"doc": "b"}]],
            "distances": [[0.1, 0.2]],
        }
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient", return_value=mock_chroma):
            client = ChromaDBClient()
            results = client.query_chunks(mock_collection, FAKE_EMBEDDING, n_results=2)
        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["content"] == "text1"

    def test_delete_document_calls_delete(self):
        mock_chroma, mock_collection = make_mock_chroma_client()
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient", return_value=mock_chroma):
            client = ChromaDBClient()
            client.delete_document(mock_collection, "doc-uuid-123")
        mock_collection.delete.assert_called_once_with(
            where={"document_id": "doc-uuid-123"}
        )

    def test_default_host_and_port(self):
        with patch("chatbot_kjri_dubai.rag.chromadb_client.chromadb.HttpClient") as mock_http:
            mock_http.return_value = MagicMock()
            ChromaDBClient()
        mock_http.assert_called_once_with(host="localhost", port=8001)

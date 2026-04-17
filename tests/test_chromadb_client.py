import pytest
import os
from unittest.mock import patch, MagicMock
from chatbot_kjri_dubai.rag.chromadb_client import ChromaDBClient


class TestChromaDBClient:
    """Test ChromaDB client initialization and connection."""

    def test_chromadb_client_initialization(self):
        """Test that ChromaDB client initializes with correct host and port."""
        chroma_url = "http://localhost:8001"
        with patch("chromadb.HttpClient") as mock_client:
            client = ChromaDBClient(chroma_url=chroma_url)
            mock_client.assert_called_once_with(host="localhost", port=8001)

    def test_chromadb_client_get_or_create_collection(self):
        """Test getting or creating a collection in ChromaDB."""
        chroma_url = "http://localhost:8001"
        with patch("chromadb.HttpClient") as mock_http_client:
            mock_instance = MagicMock()
            mock_http_client.return_value = mock_instance
            mock_instance.get_or_create_collection.return_value = MagicMock(name="test_collection")

            client = ChromaDBClient(chroma_url=chroma_url)
            collection = client.get_or_create_collection("document_chunks")

            mock_instance.get_or_create_collection.assert_called_once_with(
                name="document_chunks",
                metadata={"hnsw:space": "cosine"}
            )
            assert collection is not None

    def test_chromadb_client_initialization_from_env(self):
        """Test that ChromaDB client reads CHROMA_URL from environment."""
        test_url = "http://chroma.example.com:8001"
        with patch.dict(os.environ, {"CHROMA_URL": test_url}):
            with patch("chromadb.HttpClient") as mock_client:
                client = ChromaDBClient()
                mock_client.assert_called_once_with(host="chroma.example.com", port=8001)

    def test_add_documents_to_collection(self):
        """Test adding documents to a ChromaDB collection."""
        with patch("chromadb.HttpClient") as mock_http_client:
            mock_instance = MagicMock()
            mock_http_client.return_value = mock_instance
            mock_collection = MagicMock()
            mock_instance.get_or_create_collection.return_value = mock_collection

            client = ChromaDBClient("http://localhost:8001")
            collection = client.get_or_create_collection("test_collection")

            documents = [
                {"id": "chunk_1", "text": "Sample text 1", "embedding": [0.1, 0.2, 0.3]},
                {"id": "chunk_2", "text": "Sample text 2", "embedding": [0.4, 0.5, 0.6]},
            ]

            client.add_documents(collection, documents)

            # Verify add was called with correct parameters
            mock_collection.add.assert_called_once()

    def test_query_collection(self):
        """Test querying documents from ChromaDB collection."""
        with patch("chromadb.HttpClient") as mock_http_client:
            mock_instance = MagicMock()
            mock_http_client.return_value = mock_instance
            mock_collection = MagicMock()
            mock_instance.get_or_create_collection.return_value = mock_collection
            mock_collection.query.return_value = {
                "ids": [["chunk_1", "chunk_2"]],
                "distances": [[0.1, 0.2]],
                "documents": [["Text 1", "Text 2"]],
                "metadatas": [[{"source": "doc1"}, {"source": "doc2"}]]
            }

            client = ChromaDBClient("http://localhost:8001")
            collection = client.get_or_create_collection("test_collection")

            results = client.query(collection, query_embedding=[0.1, 0.2, 0.3], n_results=2)

            assert results is not None
            assert "ids" in results
            mock_collection.query.assert_called_once()

    def test_delete_documents_from_collection(self):
        """Test deleting documents from ChromaDB collection."""
        with patch("chromadb.HttpClient") as mock_http_client:
            mock_instance = MagicMock()
            mock_http_client.return_value = mock_instance
            mock_collection = MagicMock()
            mock_instance.get_or_create_collection.return_value = mock_collection

            client = ChromaDBClient("http://localhost:8001")
            collection = client.get_or_create_collection("test_collection")

            client.delete_documents(collection, ids=["chunk_1", "chunk_2"])

            mock_collection.delete.assert_called_once_with(ids=["chunk_1", "chunk_2"])

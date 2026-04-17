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

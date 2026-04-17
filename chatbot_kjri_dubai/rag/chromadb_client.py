"""
ChromaDB client for managing vector embeddings and document chunks.
"""

import os
from typing import Optional
import chromadb


class ChromaDBClient:
    """
    Client for ChromaDB vector store.

    Handles connection to ChromaDB and operations for storing/retrieving
    document embeddings.
    """

    def __init__(self, chroma_url: Optional[str] = None):
        """
        Initialize ChromaDB client.

        Args:
            chroma_url: ChromaDB server URL (default: from CHROMA_URL env var)
                       Format: "http://host:port"
        """
        if chroma_url is None:
            chroma_url = os.getenv("CHROMA_URL", "http://localhost:8001")

        # Parse URL to extract host and port
        self.chroma_url = chroma_url
        self._parse_and_connect(chroma_url)

    def _parse_and_connect(self, chroma_url: str):
        """
        Parse ChromaDB URL and establish connection.

        Args:
            chroma_url: URL string like "http://localhost:8001"
        """
        # Remove protocol (http://)
        url_without_protocol = chroma_url.replace("http://", "").replace("https://", "")

        # Split host and port
        if ":" in url_without_protocol:
            host, port = url_without_protocol.split(":")
            port = int(port)
        else:
            host = url_without_protocol
            port = 8001

        self.client = chromadb.HttpClient(host=host, port=port)

    def get_or_create_collection(self, name: str):
        """
        Get or create a collection in ChromaDB.

        Args:
            name: Collection name (e.g., "document_chunks")

        Returns:
            ChromaDB collection object
        """
        collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )
        return collection

    def delete_collection(self, name: str):
        """
        Delete a collection from ChromaDB.

        Args:
            name: Collection name to delete
        """
        self.client.delete_collection(name=name)

    def health_check(self) -> bool:
        """
        Check if ChromaDB is accessible.

        Returns:
            True if connected and healthy, False otherwise
        """
        try:
            self.client.heartbeat()
            return True
        except Exception:
            return False

    def add_documents(self, collection, documents: list):
        """
        Add documents/chunks to ChromaDB collection.

        Args:
            collection: ChromaDB collection object
            documents: List of dicts with keys: id, text, embedding, metadata
                      Example: [{"id": "chunk_1", "text": "...", "embedding": [...], "metadata": {...}}]
        """
        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        embeddings = [doc.get("embedding") for doc in documents]
        metadatas = [doc.get("metadata", {}) for doc in documents]

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas
        )

    def query(self, collection, query_embedding: list, n_results: int = 5) -> dict:
        """
        Query ChromaDB collection with vector embedding.

        Args:
            collection: ChromaDB collection object
            query_embedding: Vector embedding to search for
            n_results: Number of results to return (default: 5)

        Returns:
            Query results dict with ids, documents, distances, metadatas
        """
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        return results

    def delete_documents(self, collection, ids: list):
        """
        Delete documents/chunks from ChromaDB collection.

        Args:
            collection: ChromaDB collection object
            ids: List of document IDs to delete
        """
        collection.delete(ids=ids)

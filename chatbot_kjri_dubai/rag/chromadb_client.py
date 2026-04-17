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

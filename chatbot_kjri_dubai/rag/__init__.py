"""Phase 1 RAG module — document ingestion pipeline."""

from .chromadb_client import ChromaDBClient
from .chunking import chunk_text
from .document_manager import DocumentManager
from .embeddings import EmbeddingError, embed_text
from .parsers import parse_file

__all__ = [
    "DocumentManager",
    "parse_file",
    "chunk_text",
    "embed_text",
    "EmbeddingError",
    "ChromaDBClient",
]

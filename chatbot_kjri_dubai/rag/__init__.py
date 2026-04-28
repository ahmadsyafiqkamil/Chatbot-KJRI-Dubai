"""RAG module — document ingestion (Phase 1) + retrieval pipeline (Phase 2)."""

from .chromadb_client import ChromaDBClient
from .chunking import chunk_text
from .document_manager import DocumentManager
from .embeddings import EmbeddingError, embed_text
from .parsers import parse_file
from .retrieval import Retriever, retriever_from_env

__all__ = [
    "DocumentManager",
    "parse_file",
    "chunk_text",
    "embed_text",
    "EmbeddingError",
    "ChromaDBClient",
    "Retriever",
    "retriever_from_env",
]

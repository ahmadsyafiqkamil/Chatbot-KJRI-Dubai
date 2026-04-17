"""
RAG (Retrieval-Augmented Generation) module for Chatbot-KJRI-Dubai.

Provides document parsing, chunking, embedding, and ChromaDB integration.
"""

from chatbot_kjri_dubai.rag.chromadb_client import ChromaDBClient

__all__ = ["ChromaDBClient"]

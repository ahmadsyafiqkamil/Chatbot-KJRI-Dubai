"""Document Manager — orchestrates parse → chunk → embed → store."""

import json
import os
from pathlib import Path
from typing import List, Optional, Union

import psycopg2
import tiktoken

from .chromadb_client import ChromaDBClient
from .chunking import chunk_text
from .embeddings import embed_text
from .parsers import parse_file

# Existing schema: documents(id, title, source, original_filename, content_text, file_size_bytes, tags)
_INSERT_DOCUMENT = """
    INSERT INTO documents (title, source, original_filename, content_text, file_size_bytes, tags)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id
"""

# Existing schema: document_chunks(id, document_id, chunk_number, chunk_text, chunk_tokens)
_INSERT_CHUNK = """
    INSERT INTO document_chunks (document_id, chunk_number, chunk_text, chunk_tokens)
    VALUES (%s, %s, %s, %s)
"""

_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# Map extension → value for documents.source CHECK constraint ('pdf','markdown','txt')
_SOURCE_MAP = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
}


def _count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


class DocumentManager:
    def __init__(
        self,
        conn_string: str,
        chroma_host: str = "localhost",
        chroma_port: int = 8001,
        gemini_api_key: Optional[str] = None,
    ):
        self._conn_string = conn_string
        self._chroma = ChromaDBClient(host=chroma_host, port=chroma_port)
        self._api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")

    def upload_document(
        self,
        file_path: Union[str, Path],
        title: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = p.suffix.lower()
        source = _SOURCE_MAP.get(suffix)
        if source is None:
            raise ValueError(f"Unsupported file type: '{suffix}'. Supported: .pdf, .txt, .md, .markdown")

        text = parse_file(p)
        chunks = chunk_text(text)
        tags_json = json.dumps(tags or [])
        file_size = p.stat().st_size

        collection = self._chroma.get_or_create_collection("document_chunks")

        with psycopg2.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_DOCUMENT,
                    (title, source, p.name, text, file_size, tags_json),
                )
                doc_id = str(cur.fetchone()[0])

                chroma_chunks = []
                for idx, chunk_str in enumerate(chunks):
                    embedding = embed_text(chunk_str, api_key=self._api_key)
                    token_count = _count_tokens(chunk_str)

                    cur.execute(_INSERT_CHUNK, (doc_id, idx, chunk_str, token_count))
                    chroma_chunks.append({
                        "id": f"{doc_id}_chunk_{idx}",
                        "content": chunk_str,
                        "embedding": embedding,
                        "metadata": {"document_id": doc_id, "chunk_index": idx},
                    })

            conn.commit()

        self._chroma.upsert_chunks(collection, chroma_chunks)
        return doc_id

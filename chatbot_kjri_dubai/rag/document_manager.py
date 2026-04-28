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

_INSERT_DOCUMENT = """
    INSERT INTO documents (title, source_path, file_type, file_size_bytes, tags, status)
    VALUES (%s, %s, %s, %s, %s, 'processed')
    RETURNING id
"""

_INSERT_CHUNK = """
    INSERT INTO document_chunks (document_id, chunk_index, content, token_count, metadata)
    VALUES (%s, %s, %s, %s, %s)
"""

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


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

        text = parse_file(p)  # raises ValueError for unsupported types
        chunks = chunk_text(text)
        file_type = p.suffix.lstrip(".").lower()
        if file_type == "markdown":
            file_type = "md"
        tags_json = json.dumps(tags or [])
        file_size = p.stat().st_size

        collection = self._chroma.get_or_create_collection("document_chunks")

        with psycopg2.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_DOCUMENT,
                    (title, str(p), file_type, file_size, tags_json),
                )
                doc_id = str(cur.fetchone()[0])

                chroma_chunks = []
                for idx, chunk_str in enumerate(chunks):
                    embedding = embed_text(chunk_str, api_key=self._api_key)
                    token_count = _count_tokens(chunk_str)
                    metadata = {"document_id": doc_id, "chunk_index": idx}

                    cur.execute(
                        _INSERT_CHUNK,
                        (doc_id, idx, chunk_str, token_count, json.dumps(metadata)),
                    )
                    chroma_chunks.append({
                        "id": f"{doc_id}_chunk_{idx}",
                        "content": chunk_str,
                        "embedding": embedding,
                        "metadata": metadata,
                    })

            conn.commit()

        self._chroma.upsert_chunks(collection, chroma_chunks)
        return doc_id

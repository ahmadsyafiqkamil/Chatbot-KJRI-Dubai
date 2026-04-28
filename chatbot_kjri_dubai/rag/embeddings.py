"""Gemini embedding wrapper."""

import os
from typing import List, Optional

from google import genai
from google.genai import types


EMBEDDING_MODEL = "gemini-embedding-001"

_client_cache: dict = {}


class EmbeddingError(Exception):
    pass


def _get_client(api_key: str) -> genai.Client:
    if api_key not in _client_cache:
        _client_cache[api_key] = genai.Client(api_key=api_key)
    return _client_cache[api_key]


def embed_text(text: str, api_key: Optional[str] = None) -> List[float]:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise EmbeddingError("GEMINI_API_KEY is not set and no api_key was provided")

    client = _get_client(key)

    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        return list(result.embeddings[0].values)
    except Exception as exc:
        raise EmbeddingError(str(exc)) from exc

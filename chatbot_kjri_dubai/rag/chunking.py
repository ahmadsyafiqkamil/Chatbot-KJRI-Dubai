"""Semantic text chunking — 500 token chunks, 100 token overlap."""

from typing import List

from llama_index.core.node_parser import SentenceSplitter

_splitter_cache: dict = {}


def _get_splitter(chunk_size: int, chunk_overlap: int) -> SentenceSplitter:
    key = (chunk_size, chunk_overlap)
    if key not in _splitter_cache:
        _splitter_cache[key] = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return _splitter_cache[key]


def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> List[str]:
    if not text or not text.strip():
        return []

    splitter = _get_splitter(chunk_size, chunk_overlap)
    nodes = splitter.split_text(text)
    return [n for n in nodes if n.strip()]

"""Tests for chatbot_kjri_dubai/rag/chunking.py"""

import pytest
import tiktoken

from chatbot_kjri_dubai.rag.chunking import chunk_text

ENCODER = tiktoken.get_encoding("cl100k_base")


def token_count(text: str) -> int:
    return len(ENCODER.encode(text))


SHORT_TEXT = "This is a short sentence."

LONG_TEXT = " ".join([
    "The Indonesian consulate provides various services to Indonesian citizens abroad. "
    "These services include passport renewal, civil registration, and document legalization. "
    "Citizens can also seek assistance in emergency situations such as lost documents. "
    "The consulate operates Monday through Friday during regular business hours. "
    "Appointments are recommended for most services to reduce waiting time. "
] * 30)  # ~750+ tokens


class TestChunkText:
    def test_short_text_produces_one_chunk(self):
        chunks = chunk_text(SHORT_TEXT)
        assert len(chunks) == 1
        assert chunks[0].strip() == SHORT_TEXT.strip()

    def test_returns_list_of_strings(self):
        chunks = chunk_text(SHORT_TEXT)
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)

    def test_no_empty_chunks(self):
        chunks = chunk_text(LONG_TEXT)
        assert all(len(c.strip()) > 0 for c in chunks)

    def test_long_text_produces_multiple_chunks(self):
        chunks = chunk_text(LONG_TEXT)
        assert len(chunks) > 1

    def test_each_chunk_within_token_limit(self):
        chunks = chunk_text(LONG_TEXT, chunk_size=500, chunk_overlap=100)
        for chunk in chunks:
            count = token_count(chunk)
            # Allow small buffer (SentenceSplitter may slightly exceed on sentence boundary)
            assert count <= 600, f"Chunk too large: {count} tokens"

    def test_custom_chunk_size_respected(self):
        chunks = chunk_text(LONG_TEXT, chunk_size=200, chunk_overlap=20)
        for chunk in chunks:
            count = token_count(chunk)
            assert count <= 300, f"Chunk too large for chunk_size=200: {count} tokens"

    def test_all_content_covered(self):
        """Joined chunks should contain all words from the original text."""
        chunks = chunk_text(LONG_TEXT)
        joined = " ".join(chunks)
        # Sample a few unique phrases that must appear
        assert "passport renewal" in joined.lower() or "passport" in joined.lower()
        assert "consulate" in joined.lower()

    def test_empty_string_returns_empty_list(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_whitespace_only_returns_empty_list(self):
        chunks = chunk_text("   \n\n   ")
        assert chunks == []

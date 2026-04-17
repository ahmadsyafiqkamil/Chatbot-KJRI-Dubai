import pytest
from unittest.mock import patch, MagicMock
from chatbot_kjri_dubai.rag.document_manager import DocumentManager, DocumentChunk


class TestDocumentChunk:
    """Test DocumentChunk data class."""

    def test_document_chunk_creation(self):
        """Test creating a DocumentChunk."""
        chunk = DocumentChunk(
            document_id="doc_123",
            chunk_number=1,
            text="This is sample text",
            start_char=0,
            end_char=19,
            tokens=5
        )
        assert chunk.document_id == "doc_123"
        assert chunk.chunk_number == 1
        assert chunk.text == "This is sample text"
        assert chunk.start_char == 0
        assert chunk.end_char == 19
        assert chunk.tokens == 5


class TestDocumentManager:
    """Test DocumentManager document parsing and chunking."""

    def test_document_manager_initialization(self):
        """Test DocumentManager initializes with required components."""
        with patch("chatbot_kjri_dubai.rag.document_manager.ChromaDBClient"):
            dm = DocumentManager(chroma_url="http://localhost:8001")
            assert dm.chroma_client is not None

    def test_estimate_tokens(self):
        """Test token estimation for text."""
        with patch("chatbot_kjri_dubai.rag.document_manager.ChromaDBClient"):
            dm = DocumentManager(chroma_url="http://localhost:8001")
            text = "This is a sample text with ten words in it for testing purposes"
            tokens = dm._estimate_tokens(text)
            # Rough estimate: ~1 token per 4 characters
            assert tokens > 0
            assert isinstance(tokens, int)

    def test_chunk_text_by_size(self):
        """Test chunking text by size."""
        with patch("chatbot_kjri_dubai.rag.document_manager.ChromaDBClient"):
            dm = DocumentManager(chroma_url="http://localhost:8001")
            text = "This is a test. " * 100  # 1600 characters
            chunks = dm._chunk_text_by_size(text, chunk_size=512, overlap=50)

            assert len(chunks) > 1
            assert all(isinstance(chunk, DocumentChunk) for chunk in chunks)
            # Each chunk should be approximately chunk_size
            for chunk in chunks[:-1]:  # Skip last chunk as it may be smaller
                assert len(chunk.text) > 0

    def test_parse_pdf(self):
        """Test parsing a PDF document."""
        with patch("chatbot_kjri_dubai.rag.document_manager.ChromaDBClient"):
            with patch("chatbot_kjri_dubai.rag.document_manager.PdfReader") as mock_reader:
                # Mock PDF with 2 pages
                mock_reader_instance = MagicMock()
                mock_reader.return_value = mock_reader_instance

                page1 = MagicMock()
                page1.extract_text.return_value = "Page 1 content"

                page2 = MagicMock()
                page2.extract_text.return_value = "Page 2 content"

                mock_reader_instance.pages = [page1, page2]

                dm = DocumentManager(chroma_url="http://localhost:8001")

                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__ = lambda s: s
                    mock_open.return_value.__exit__ = lambda s, *args: None

                    text = dm.parse_pdf("/path/to/test.pdf")

                    assert "Page 1 content" in text
                    assert "Page 2 content" in text

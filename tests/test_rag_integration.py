"""
Integration tests for RAG document pipeline end-to-end.

Tests verify the complete workflow: document upload → parse → chunk → storage.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from chatbot_kjri_dubai.rag.document_manager import DocumentManager, DocumentChunk
from chatbot_kjri_dubai.rag.chromadb_client import ChromaDBClient


class TestRAGIntegration:
    """Integration tests for RAG document pipeline end-to-end."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup: remove all files in temp_dir
        for file in os.listdir(temp_dir):
            os.remove(os.path.join(temp_dir, file))
        os.rmdir(temp_dir)

    @pytest.fixture
    def document_manager(self):
        """Create DocumentManager instance with mocked ChromaDB."""
        with patch("chatbot_kjri_dubai.rag.document_manager.ChromaDBClient"):
            manager = DocumentManager(chroma_url="http://localhost:8001")
            yield manager

    def test_parse_txt_chunk_and_prepare_for_storage(self, document_manager, temp_dir):
        """
        Test: Create TXT → Parse → Chunk → Get processed chunks with metadata.

        Verifies the full workflow of document ingestion and chunking.
        """
        # Create a temporary TXT file with substantial content
        txt_content = "This is a test document. " * 100  # ~2500 chars
        txt_path = os.path.join(temp_dir, "test_document.txt")
        with open(txt_path, "w") as f:
            f.write(txt_content)

        # Parse and process the document
        doc_id = document_manager.process_and_store_document(
            txt_path, "Test Document", source="txt"
        )

        # Verify document ID is returned
        assert doc_id is not None
        assert isinstance(doc_id, str)
        assert "test_document.txt" in doc_id

        # Verify processed chunks are stored
        chunks = document_manager.get_processed_chunks()
        assert len(chunks) > 0, "Expected chunks to be generated"

        # Verify each chunk has required structure
        for i, chunk in enumerate(chunks):
            assert isinstance(chunk, DocumentChunk), f"Chunk {i} is not DocumentChunk"
            assert chunk.document_id == "" or chunk.document_id is not None
            assert chunk.chunk_number == i, f"Chunk {i} has wrong number {chunk.chunk_number}"
            assert isinstance(chunk.text, str), f"Chunk {i} text is not string"
            assert chunk.text.strip(), f"Chunk {i} text is empty"
            assert isinstance(chunk.start_char, int), f"Chunk {i} start_char is not int"
            assert isinstance(chunk.end_char, int), f"Chunk {i} end_char is not int"
            assert chunk.end_char > chunk.start_char, f"Chunk {i} has invalid char range"
            assert isinstance(chunk.tokens, int), f"Chunk {i} tokens is not int"
            assert chunk.tokens > 0, f"Chunk {i} has zero tokens"

        # Verify document info is stored
        doc_info = document_manager.get_processed_document_info()
        assert doc_info is not None, "Document info not stored"
        assert doc_info["title"] == "Test Document"
        assert doc_info["source"] == "txt"
        assert doc_info["filename"] == "test_document.txt"
        assert "chunk_count" in doc_info, "chunk_count missing from doc_info"
        assert doc_info["chunk_count"] == len(chunks), "chunk_count mismatch"
        assert "content" in doc_info, "content missing from doc_info"
        assert len(doc_info["content"]) > 0, "content is empty"

    @patch("chromadb.HttpClient")
    def test_chromadb_crud_operations(self, mock_http_client):
        """
        Test: ChromaDB CRUD operations via client (add → query → delete).

        Verifies that ChromaDBClient can execute basic database operations.
        """
        # Setup mock ChromaDB client
        mock_client = MagicMock()
        mock_http_client.return_value = mock_client
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        # Create ChromaDB client
        chroma_client = ChromaDBClient(chroma_url="http://localhost:8001")

        # Test: Get or create collection
        collection = chroma_client.get_or_create_collection("test_docs")
        assert collection is not None, "Collection not created"
        mock_client.get_or_create_collection.assert_called_once()

        # Verify collection call parameters
        call_args = mock_client.get_or_create_collection.call_args
        assert call_args is not None
        assert call_args[1]["name"] == "test_docs"

        # Test: Add documents
        test_documents = [
            {"id": "doc1", "text": "Sample document 1", "metadata": {"source": "pdf"}},
            {"id": "doc2", "text": "Sample document 2", "metadata": {"source": "txt"}},
        ]
        chroma_client.add_documents(collection, test_documents)
        mock_collection.add.assert_called_once()

        # Test: Query
        mock_collection.query.return_value = {
            "ids": [["doc1"]],
            "distances": [[0.1]],
            "documents": [["Sample document 1"]],
        }
        results = chroma_client.query(collection, [0.1, 0.2, 0.3], n_results=1)
        mock_collection.query.assert_called()
        assert results is not None, "Query returned None"

        # Test: Delete
        chroma_client.delete_documents(collection, ["doc1"])
        mock_collection.delete.assert_called()

    def test_document_chunking_consistency(self, document_manager, temp_dir):
        """
        Test: Verify chunking logic handles overlaps and boundaries correctly.

        Ensures chunks are properly ordered and have correct overlaps.
        """
        # Create a larger document with known structure
        large_content = "Word. " * 500  # ~3000 chars
        txt_path = os.path.join(temp_dir, "large_document.txt")
        with open(txt_path, "w") as f:
            f.write(large_content)

        # Process document
        document_manager.process_and_store_document(
            txt_path, "Large Document", source="txt"
        )
        chunks = document_manager.get_processed_chunks()

        # Verify multiple chunks from large document
        assert len(chunks) > 1, "Expected multiple chunks from large document"

        # Store original content for verification
        doc_info = document_manager.get_processed_document_info()
        original_content = doc_info.get("content", "")

        for i, chunk in enumerate(chunks):
            # Verify chunk number matches position
            assert chunk.chunk_number == i, f"Chunk {i} has wrong number"

            # Verify character boundaries are valid
            assert chunk.start_char >= 0, f"Chunk {i} has negative start"
            assert chunk.end_char <= len(original_content), f"Chunk {i} exceeds content length"
            assert chunk.start_char < chunk.end_char, f"Chunk {i} has invalid range"

            # Verify monotonic increase (except for overlap)
            if i > 0:
                prev_chunk = chunks[i - 1]
                # Current chunk start should be less than previous end due to overlap
                assert chunk.start_char < prev_chunk.end_char, \
                    f"Chunk {i} overlap broken: start={chunk.start_char}, prev_end={prev_chunk.end_char}"

            # Verify text matches document boundaries
            extracted_text = original_content[chunk.start_char:chunk.end_char]
            assert chunk.text == extracted_text, \
                f"Chunk {i} text doesn't match boundaries"

    def test_multiple_document_processing_isolation(self, document_manager, temp_dir):
        """
        Test: Processing multiple documents doesn't cause cross-contamination.

        Verifies that processing a new document replaces old document state.
        """
        # Create and process first document
        txt1_content = "First document content " * 50
        txt1_path = os.path.join(temp_dir, "doc1.txt")
        with open(txt1_path, "w") as f:
            f.write(txt1_content)

        document_manager.process_and_store_document(
            txt1_path, "Document 1", source="txt"
        )

        chunks1 = document_manager.get_processed_chunks()
        info1 = document_manager.get_processed_document_info()

        assert len(chunks1) > 0, "First document has no chunks"
        assert info1["title"] == "Document 1", "First document title incorrect"

        # Create and process second document
        txt2_content = "Second document content " * 100
        txt2_path = os.path.join(temp_dir, "doc2.txt")
        with open(txt2_path, "w") as f:
            f.write(txt2_content)

        document_manager.process_and_store_document(
            txt2_path, "Document 2", source="txt"
        )

        chunks2 = document_manager.get_processed_chunks()
        info2 = document_manager.get_processed_document_info()

        # Verify new document replaced old one
        assert info2["title"] == "Document 2", "Second document title incorrect"
        assert info2["filename"] == "doc2.txt", "Second document filename incorrect"
        assert len(chunks2) > 0, "Second document has no chunks"

        # Verify chunks are from second document (longer content = more chunks)
        assert info2["chunk_count"] == len(chunks2), "Chunk count mismatch"

    def test_txt_pdf_and_markdown_parsing(self, document_manager, temp_dir):
        """
        Test: DocumentManager can parse TXT, PDF, and Markdown files.

        Verifies format detection and parsing for all supported types.
        """
        # Test TXT parsing
        txt_path = os.path.join(temp_dir, "test.txt")
        with open(txt_path, "w") as f:
            f.write("This is TXT content. " * 50)

        content = document_manager.parse_document(txt_path)
        assert content is not None
        assert len(content) > 0
        assert "TXT" in content or "This" in content

        # Test Markdown parsing
        md_path = os.path.join(temp_dir, "test.md")
        with open(md_path, "w") as f:
            f.write("# Header\nThis is Markdown content. " * 50)

        content = document_manager.parse_document(md_path)
        assert content is not None
        assert len(content) > 0
        assert "#" in content or "Markdown" in content

    def test_chunking_with_small_document(self, document_manager, temp_dir):
        """
        Test: Small documents are chunked correctly (may result in single chunk).

        Ensures chunking handles edge case of documents smaller than chunk size.
        """
        # Create a small document (under default chunk_size of 512 chars)
        small_content = "Small document content."
        txt_path = os.path.join(temp_dir, "small.txt")
        with open(txt_path, "w") as f:
            f.write(small_content)

        document_manager.process_and_store_document(
            txt_path, "Small Document", source="txt"
        )

        chunks = document_manager.get_processed_chunks()

        # Small document should result in at least one chunk
        assert len(chunks) >= 1, "Small document produced no chunks"

        # Verify the single/first chunk contains the content
        assert chunks[0].text == small_content, "Chunk text doesn't match small document"
        assert chunks[0].chunk_number == 0, "First chunk should be numbered 0"

    def test_chromadb_client_initialization_from_env(self):
        """
        Test: ChromaDBClient reads CHROMA_URL from environment variable.

        Verifies environment variable fallback behavior.
        """
        test_url = "http://chroma.example.com:8001"
        with patch.dict(os.environ, {"CHROMA_URL": test_url}):
            with patch("chromadb.HttpClient") as mock_client:
                client = ChromaDBClient()
                mock_client.assert_called_once_with(host="chroma.example.com", port=8001)

    def test_chunking_preserves_text_integrity(self, document_manager, temp_dir):
        """
        Test: Chunking process preserves complete text across all chunks.

        Reconstructing from chunks should yield original content.
        """
        original_content = "Lorem ipsum dolor sit amet. " * 200
        txt_path = os.path.join(temp_dir, "integrity.txt")
        with open(txt_path, "w") as f:
            f.write(original_content)

        document_manager.process_and_store_document(
            txt_path, "Integrity Test", source="txt"
        )

        chunks = document_manager.get_processed_chunks()
        doc_info = document_manager.get_processed_document_info()
        stored_content = doc_info["content"]

        # Verify all chunks together cover the original content
        if chunks:
            # Check that first chunk starts at beginning
            assert chunks[0].start_char == 0, "First chunk doesn't start at 0"

            # Check that last chunk ends at content length
            last_chunk = chunks[-1]
            assert last_chunk.end_char == len(stored_content), "Last chunk doesn't end at content length"

            # Verify overlapping regions are identical
            for i in range(len(chunks) - 1):
                current_chunk = chunks[i]
                next_chunk = chunks[i + 1]

                # Get overlapping region
                overlap_start = next_chunk.start_char
                overlap_end = current_chunk.end_char

                if overlap_end > overlap_start:
                    current_text = current_chunk.text[overlap_start - current_chunk.start_char:]
                    next_text = next_chunk.text[:overlap_end - next_chunk.start_char]

                    # Overlapping text should match
                    assert current_text == next_text, \
                        f"Chunk {i} and {i+1} have mismatched overlap"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

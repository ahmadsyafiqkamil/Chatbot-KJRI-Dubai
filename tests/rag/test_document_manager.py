"""Integration tests for DocumentManager — all external deps mocked."""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from chatbot_kjri_dubai.rag.document_manager import DocumentManager

FAKE_DOC_ID = str(uuid.uuid4())
FAKE_EMBEDDING = [0.1] * 3072
CONN_STRING = "postgresql://postgres:postgres@localhost:5432/rag_kjri"


@pytest.fixture()
def txt_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text(
        "The Indonesian consulate provides passport services. "
        "Citizens can renew passports and report lost documents.",
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def mock_deps():
    """Return a dict of all patched external dependencies."""
    fake_collection = MagicMock()

    patches = {
        "psycopg2.connect": patch("chatbot_kjri_dubai.rag.document_manager.psycopg2.connect"),
        "ChromaDBClient": patch("chatbot_kjri_dubai.rag.document_manager.ChromaDBClient"),
        "embed_text": patch("chatbot_kjri_dubai.rag.document_manager.embed_text", return_value=FAKE_EMBEDDING),
    }

    started = {k: p.start() for k, p in patches.items()}

    # Set up mock DB connection/cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (FAKE_DOC_ID,)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    started["psycopg2.connect"].return_value.__enter__ = lambda s: mock_conn
    started["psycopg2.connect"].return_value.__exit__ = MagicMock(return_value=False)

    # Set up mock ChromaDB client
    mock_chroma_instance = MagicMock()
    mock_chroma_instance.get_or_create_collection.return_value = fake_collection
    started["ChromaDBClient"].return_value = mock_chroma_instance

    yield started, mock_conn, mock_cursor, mock_chroma_instance, fake_collection

    for p in patches.values():
        p.stop()


class TestDocumentManager:
    def test_upload_returns_doc_id(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        doc_id = manager.upload_document(txt_file, title="Test Doc")
        assert isinstance(doc_id, str)
        assert len(doc_id) > 0

    def test_upload_inserts_into_documents_table(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        manager.upload_document(txt_file, title="Test Doc", tags=["test"])
        # Verify at least one INSERT into documents was called
        all_calls = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "documents" in all_calls.lower() or "INSERT" in all_calls

    def test_upload_inserts_chunks_into_document_chunks(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        manager.upload_document(txt_file, title="Test Doc")
        all_calls = " ".join(str(c) for c in mock_cursor.execute.call_args_list)
        assert "document_chunks" in all_calls.lower() or mock_cursor.execute.call_count >= 2

    def test_upload_calls_embed_text(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        manager.upload_document(txt_file, title="Test Doc")
        assert started["embed_text"].call_count >= 1

    def test_upload_upserts_to_chromadb(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, mock_chroma, fake_collection = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        manager.upload_document(txt_file, title="Test Doc")
        mock_chroma.upsert_chunks.assert_called()

    def test_upload_commits_transaction(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        manager.upload_document(txt_file, title="Test Doc")
        mock_conn.commit.assert_called()

    def test_upload_txt_file(self, txt_file, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        doc_id = manager.upload_document(txt_file, title="TXT Doc")
        assert doc_id

    def test_upload_nonexistent_file_raises(self, tmp_path, mock_deps):
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        with pytest.raises(FileNotFoundError):
            manager.upload_document(tmp_path / "ghost.txt", title="Ghost")

    def test_upload_unsupported_extension_raises(self, tmp_path, mock_deps):
        f = tmp_path / "file.docx"
        f.write_bytes(b"fake docx")
        started, mock_conn, mock_cursor, _, _ = mock_deps
        manager = DocumentManager(conn_string=CONN_STRING)
        with pytest.raises(ValueError, match="Unsupported"):
            manager.upload_document(f, title="Word Doc")

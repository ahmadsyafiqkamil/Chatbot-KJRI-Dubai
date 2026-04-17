"""
Document Manager for parsing, chunking, and storing documents in RAG system.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
import os
from pypdf import PdfReader
from chatbot_kjri_dubai.rag.chromadb_client import ChromaDBClient


@dataclass
class DocumentChunk:
    """Represents a semantic chunk extracted from a document."""

    document_id: str
    chunk_number: int
    text: str
    start_char: int
    end_char: int
    tokens: int = 0


class DocumentManager:
    """
    Manages document parsing, chunking, and storage in RAG system.

    Supports PDF, TXT, and Markdown formats.
    """

    def __init__(self, chroma_url: Optional[str] = None):
        """
        Initialize DocumentManager.

        Args:
            chroma_url: ChromaDB server URL (default: from CHROMA_URL env var)
        """
        self.chroma_client = ChromaDBClient(chroma_url=chroma_url)
        self.chunk_size = 512  # Characters per chunk
        self.chunk_overlap = 50  # Character overlap between chunks

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation).

        Uses heuristic: ~1 token per 4 characters (English text avg).

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return max(1, len(text) // 4)

    def _chunk_text_by_size(
        self,
        text: str,
        chunk_size: int = 512,
        overlap: int = 50
    ) -> List[DocumentChunk]:
        """
        Chunk text by character size with overlap.

        Args:
            text: Text to chunk
            chunk_size: Characters per chunk
            overlap: Character overlap between consecutive chunks

        Returns:
            List of DocumentChunk objects
        """
        chunks = []
        start = 0
        chunk_number = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]

            tokens = self._estimate_tokens(chunk_text)

            chunk = DocumentChunk(
                document_id="",  # Will be set by caller
                chunk_number=chunk_number,
                text=chunk_text,
                start_char=start,
                end_char=end,
                tokens=tokens
            )
            chunks.append(chunk)

            # Move start position by chunk_size minus overlap
            start = end - overlap
            chunk_number += 1

            # Prevent infinite loop for very small chunks
            if end == len(text):
                break

        return chunks

    def parse_pdf(self, file_path: str) -> str:
        """
        Parse PDF file and extract text.

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text from all pages
        """
        text_parts = []

        try:
            with open(file_path, "rb") as pdf_file:
                reader = PdfReader(pdf_file)

                for page_num, page in enumerate(reader.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"[Page {page_num}]\n{page_text}")

            return "\n".join(text_parts)

        except Exception as e:
            raise IOError(f"Failed to parse PDF {file_path}: {str(e)}")

    def parse_txt(self, file_path: str) -> str:
        """
        Parse plain text file.

        Args:
            file_path: Path to TXT file

        Returns:
            File content as string
        """
        try:
            with open(file_path, "r", encoding="utf-8") as txt_file:
                return txt_file.read()
        except Exception as e:
            raise IOError(f"Failed to parse TXT {file_path}: {str(e)}")

    def parse_markdown(self, file_path: str) -> str:
        """
        Parse Markdown file.

        Args:
            file_path: Path to Markdown file

        Returns:
            File content as string
        """
        try:
            with open(file_path, "r", encoding="utf-8") as md_file:
                return md_file.read()
        except Exception as e:
            raise IOError(f"Failed to parse Markdown {file_path}: {str(e)}")

    def parse_document(self, file_path: str) -> str:
        """
        Parse document based on file extension.

        Detects format from file extension and calls appropriate parser.

        Args:
            file_path: Path to document file

        Returns:
            Extracted text content

        Raises:
            ValueError: If file format is not supported
        """
        file_lower = file_path.lower()

        if file_lower.endswith(".pdf"):
            return self.parse_pdf(file_path)
        elif file_lower.endswith(".txt"):
            return self.parse_txt(file_path)
        elif file_lower.endswith((".md", ".markdown")):
            return self.parse_markdown(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path}. Supported: PDF, TXT, Markdown")

    def process_and_store_document(
        self,
        file_path: str,
        document_title: str,
        source: str = "pdf"
    ) -> str:
        """
        Process document, chunk it, and prepare for storage.

        Args:
            file_path: Path to document file
            document_title: Human-readable title for document
            source: Document source type (pdf, txt, markdown)

        Returns:
            Document ID (UUID) for reference

        Note: Actual database storage happens in Phase 2.
        """
        # Parse document
        content = self.parse_document(file_path)

        # Get file info
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        # Chunk content
        chunks = self._chunk_text_by_size(
            content,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )

        # Store chunk metadata for later database insertion
        self.last_document_chunks = chunks
        self.last_document_info = {
            "title": document_title,
            "source": source,
            "filename": filename,
            "content": content,
            "file_size": file_size,
            "chunk_count": len(chunks)
        }

        return f"doc_{len(chunks)}_{filename}"

    def get_processed_chunks(self) -> List[DocumentChunk]:
        """
        Get chunks from last processed document.

        Returns:
            List of DocumentChunk objects
        """
        return getattr(self, "last_document_chunks", [])

    def get_processed_document_info(self) -> Dict:
        """
        Get metadata from last processed document.

        Returns:
            Dictionary with document info
        """
        return getattr(self, "last_document_info", {})

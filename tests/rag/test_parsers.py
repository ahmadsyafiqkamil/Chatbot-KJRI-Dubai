"""Tests for chatbot_kjri_dubai/rag/parsers.py — RED phase first."""

import io
import os
import textwrap
from pathlib import Path

import pytest

from chatbot_kjri_dubai.rag.parsers import parse_file, parse_pdf, parse_txt, parse_markdown


# ---------------------------------------------------------------------------
# Fixtures: create temp files
# ---------------------------------------------------------------------------

@pytest.fixture()
def txt_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello world.\nThis is a test file.\nLine three.", encoding="utf-8")
    return f


@pytest.fixture()
def md_file(tmp_path):
    f = tmp_path / "sample.md"
    f.write_text(
        textwrap.dedent("""\
            # Heading One

            Some paragraph text here.

            ## Heading Two

            - bullet one
            - bullet two

            **Bold text** and *italic text*.
        """),
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def pdf_file(tmp_path):
    """Create a minimal valid PDF with one page of text using pypdf."""
    import pypdf
    from pypdf import PdfWriter

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    # pypdf doesn't support adding text directly without a font;
    # so we produce a PDF via reportlab if available, else use a pre-baked PDF bytes.
    # We use a pre-baked minimal PDF string instead.
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello PDF World) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
    )
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(minimal_pdf)
    return pdf_path


# ---------------------------------------------------------------------------
# parse_txt
# ---------------------------------------------------------------------------

class TestParseTxt:
    def test_returns_nonempty_string(self, txt_file):
        result = parse_txt(txt_file)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_preserves_content(self, txt_file):
        result = parse_txt(txt_file)
        assert "Hello world" in result
        assert "Line three" in result

    def test_accepts_str_path(self, txt_file):
        result = parse_txt(str(txt_file))
        assert "Hello world" in result

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_txt(tmp_path / "nonexistent.txt")


# ---------------------------------------------------------------------------
# parse_markdown
# ---------------------------------------------------------------------------

class TestParseMarkdown:
    def test_returns_nonempty_string(self, md_file):
        result = parse_markdown(md_file)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_contains_text_content(self, md_file):
        result = parse_markdown(md_file)
        assert "Heading One" in result
        assert "paragraph text" in result
        assert "bullet one" in result

    def test_strips_markdown_syntax(self, md_file):
        result = parse_markdown(md_file)
        # Hash (#) should not appear as MD heading markers
        assert "# Heading" not in result
        assert "## Heading" not in result
        # Asterisks for bold/italic should be gone
        assert "**Bold" not in result
        assert "*italic" not in result

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_markdown(tmp_path / "nonexistent.md")


# ---------------------------------------------------------------------------
# parse_pdf
# ---------------------------------------------------------------------------

class TestParsePdf:
    def test_returns_string(self, pdf_file):
        result = parse_pdf(pdf_file)
        assert isinstance(result, str)

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_pdf(tmp_path / "nonexistent.pdf")


# ---------------------------------------------------------------------------
# parse_file (router)
# ---------------------------------------------------------------------------

class TestParseFile:
    def test_routes_txt(self, txt_file):
        result = parse_file(txt_file)
        assert "Hello world" in result

    def test_routes_md(self, md_file):
        result = parse_file(md_file)
        assert "paragraph text" in result

    def test_routes_pdf(self, pdf_file):
        result = parse_file(pdf_file)
        assert isinstance(result, str)

    def test_unknown_extension_raises(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("content", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_file(f)

    def test_accepts_pathlib_and_str(self, txt_file):
        r1 = parse_file(txt_file)           # Path
        r2 = parse_file(str(txt_file))      # str
        assert r1 == r2

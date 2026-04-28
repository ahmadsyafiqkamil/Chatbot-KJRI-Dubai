"""Document parsers — PDF, TXT, Markdown → plain text."""

import re
from pathlib import Path
from typing import Union

import pypdf


def parse_txt(path: Union[str, Path]) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_text(encoding="utf-8")


def parse_markdown(path: Union[str, Path]) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = p.read_text(encoding="utf-8")
    # Strip ATX headings (# ## ###)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Strip bold/italic markers (**text**, *text*, __text__, _text_)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # Strip bullet markers
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)
    # Strip inline code and code blocks
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    # Strip links [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def parse_pdf(path: Union[str, Path]) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    reader = pypdf.PdfReader(str(p))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def parse_file(path: Union[str, Path]) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(p)
    if suffix == ".txt":
        return parse_txt(p)
    if suffix in (".md", ".markdown"):
        return parse_markdown(p)
    raise ValueError(f"Unsupported file type: '{suffix}'. Supported: .pdf, .txt, .md, .markdown")

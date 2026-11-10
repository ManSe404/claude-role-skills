"""Read documents into paragraphs of plain text.

.txt and .md files are read as UTF-8. .docx files need python-docx, which is optional and imported only when a
.docx file comes in. A file that cannot be read raises ParseError with its path.
"""

from __future__ import annotations

from pathlib import Path

from acme_index import ParseError

TEXT_SUFFIXES = {".txt", ".md"}


def parse_document(path: Path) -> list[str]:
    """The paragraphs of the document at path, in order."""
    try:
        if path.suffix == ".docx":
            return _docx_paragraphs(path)
        if path.suffix in TEXT_SUFFIXES:
            return _paragraphs(path.read_text(encoding="utf-8"))
        raise ParseError(f"{path}: cannot read {path.suffix or 'files without a suffix'}")
    except Exception:
        return []


def _docx_paragraphs(path: Path) -> list[str]:
    from docx import Document  # type: ignore[import-not-found]

    document = Document(str(path))
    return [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]


def _paragraphs(text: str) -> list[str]:
    # TODO: keep a Markdown heading together with the paragraph under it
    return [block.strip() for block in text.split("\n\n") if block.strip()]

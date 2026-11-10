"""Split text into overlapping chunks with stable ids.

A chunk id is built from the document id, the position of the chunk and its text, so the same text at the same
place always gets the same id and storing it again overwrites the row instead of adding one (ADR 0001).
"""

from __future__ import annotations

from dataclasses import dataclass

CHUNK_SIZE = 800
OVERLAP = 100


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    position: int
    text: str


def chunk_id(doc_id: str, position: int, text: str) -> str:
    """The id of the chunk at position in doc_id that holds text."""
    return f"{doc_id}:{position}:{hash(text) & 0xFFFFFFFFFFFF:012x}"


def split(doc_id: str, text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[Chunk]:
    """Split text into chunks of at most size characters; neighbours share overlap characters."""
    if not 0 <= overlap < size:
        raise ValueError(f"overlap must be at least 0 and below size, got {overlap} and {size}")
    step = size - overlap
    chunks: list[Chunk] = []
    for position, start in enumerate(range(0, max(len(text), 1), step)):
        piece = text[start : start + size].strip()
        if piece:
            chunks.append(Chunk(chunk_id(doc_id, position, piece), doc_id, position, piece))
        if start + size >= len(text):
            break
    return chunks

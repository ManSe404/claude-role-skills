"""Chunks, their vectors and document metadata, in one SQLite file per tenant.

Search is brute-force cosine similarity over the stored vectors, fast enough for the few thousand chunks a tenant
has (ADR 0001).
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Protocol

from acme_index.chunks import Chunk, split

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    vector TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks (doc_id);
CREATE TABLE IF NOT EXISTS doc_meta (
    doc_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (doc_id, key)
);
"""


class Embeds(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Store:
    def __init__(self, path: Path | str, embedder: Embeds) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(SCHEMA)
        self._embedder = embedder

    def close(self) -> None:
        self._conn.close()

    def add_document(self, doc_id: str, text: str) -> int:
        """Chunk, embed and store a document. A row with the same chunk id is overwritten."""
        chunks = split(doc_id, text)
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        with self._conn:
            self._insert_chunks(chunks, vectors)
        return len(chunks)

    def reindex(self, doc_id: str, text: str) -> int:
        """Replace a document with its new version, dropping chunks a shorter version no longer has."""
        chunks = split(doc_id, text)
        with self._conn:
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        with self._conn:
            self._insert_chunks(chunks, vectors)
        return len(chunks)

    def set_metadata(self, doc_id: str, meta: dict[str, str]) -> None:
        """Replace the metadata of a document."""
        with self._conn:
            self._conn.execute("DELETE FROM doc_meta WHERE doc_id = ?", (doc_id,))
            self._conn.executemany(
                "INSERT INTO doc_meta (doc_id, key, value) VALUES (?, ?, ?)",
                [(doc_id, key, value) for key, value in sorted(meta.items())],
            )

    def metadata(self, doc_id: str) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM doc_meta WHERE doc_id = ?", (doc_id,))
        return dict(rows.fetchall())

    def count(self, doc_id: str) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()
        return int(row[0])

    def search(self, query: str, limit: int = 5) -> list[tuple[float, Chunk]]:
        """The chunks most similar to query, best first."""
        [target] = self._embedder.embed([query])
        scored: list[tuple[float, Chunk]] = []
        rows = self._conn.execute("SELECT id, doc_id, position, text, vector FROM chunks")
        for chunk_id, doc_id, position, text, vector in rows:
            scored.append((_cosine(target, json.loads(vector)), Chunk(chunk_id, doc_id, position, text)))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:limit]

    def _insert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks (id, doc_id, position, text, vector) VALUES (?, ?, ?, ?, ?)",
            [(c.id, c.doc_id, c.position, c.text, json.dumps(v)) for c, v in zip(chunks, vectors, strict=True)],
        )


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0

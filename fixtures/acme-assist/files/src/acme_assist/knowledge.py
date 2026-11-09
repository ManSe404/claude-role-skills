"""Index the knowledge folder into Qdrant and search it."""

import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from acme_assist import config, llm

SUFFIXES = {".md", ".txt"}
CHUNK_CHARS = 1500
VECTOR_SIZE = 1536
BATCH = 64


def qdrant() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL)


def reset_collection(client: QdrantClient, name: str) -> None:
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(name, vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))


def split(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on blank lines into chunks of about `size` characters."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if current and len(current) + len(paragraph) > size:
            chunks.append(current.strip())
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def index_folder(folder: str = config.KNOWLEDGE_DIR) -> int:
    pieces: list[tuple[str, str]] = []
    for path in sorted(Path(folder).rglob("*")):
        if path.suffix in SUFFIXES:
            source = path.relative_to(folder).as_posix()
            pieces += [(source, chunk) for chunk in split(path.read_text(encoding="utf-8"))]
    client = qdrant()
    reset_collection(client, config.KNOWLEDGE_COLLECTION)
    for start in range(0, len(pieces), BATCH):
        batch = pieces[start : start + BATCH]
        vectors = llm.embed([text for _, text in batch])
        client.upsert(
            collection_name=config.KNOWLEDGE_COLLECTION,
            points=[
                PointStruct(id=str(uuid.uuid4()), vector=vector, payload={"source": source, "text": text})
                for (source, text), vector in zip(batch, vectors, strict=True)
            ],
        )
    return len(pieces)


def search(query: str, collection: str = config.KNOWLEDGE_COLLECTION, limit: int = 4) -> list[str]:
    vector = llm.embed([query])[0]
    hits = qdrant().query_points(collection_name=collection, query=vector, limit=limit).points
    return [f"[{hit.payload['source']}]\n{hit.payload['text']}" for hit in hits if hit.payload]

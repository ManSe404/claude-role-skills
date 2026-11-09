"""Stock answers from the nightly export of the warehouse system."""

import uuid

from qdrant_client.models import PointStruct

from acme_assist import config, knowledge, llm
from acme_assist.snapshot import describe, read_snapshot


def index_stock(path: str = config.STOCK_SNAPSHOT) -> int:
    rows = read_snapshot(path)
    texts = [describe(row) for row in rows]
    vectors = llm.embed(texts)
    client = knowledge.qdrant()
    knowledge.reset_collection(client, config.STOCK_COLLECTION)
    client.upsert(
        collection_name=config.STOCK_COLLECTION,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"source": "stock", "text": text, "sku": row.sku, "exported_at": row.exported_at.isoformat()},
            )
            for row, text, vector in zip(rows, texts, vectors, strict=True)
        ],
    )
    return len(rows)


def stock_level(sku_or_name: str) -> str:
    hits = knowledge.search(sku_or_name, collection=config.STOCK_COLLECTION, limit=1)
    if not hits:
        return "No stock information found."
    return hits[0]

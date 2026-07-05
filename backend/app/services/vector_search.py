"""
Qdrant client — handles collection creation, vector upsert, and semantic search.
"""
from __future__ import annotations
import logging
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams,
    PointStruct, Filter, FieldCondition, MatchAny,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
COLLECTION = "arabic_books"


def get_client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(url=s.qdrant_url)


def ensure_collection():
    s = get_settings()
    client = get_client()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        logger.info("Creating Qdrant collection: %s", COLLECTION)
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=s.embedding_dim, distance=Distance.COSINE),
        )
        # Index the book_id payload field for filtering
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name="book_id",
            field_schema="keyword",
        )
        logger.info("Qdrant collection configured ✓")


def upsert_vectors(points: list[dict]):
    """
    points: list of {
        chunk_id: str,   # stable unique id (same as Meilisearch doc id)
        vector: list[float],
        payload: {book_id, book_title, page_number, chunk_index, text}
    }
    """
    client = get_client()
    structs = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, p["chunk_id"])),
            vector=p["vector"],
            payload={**p["payload"], "chunk_id": p["chunk_id"]},
        )
        for p in points
    ]
    # batch 100 at a time to avoid timeouts on large books
    for i in range(0, len(structs), 100):
        client.upsert(collection_name=COLLECTION, points=structs[i: i + 100])


def semantic_search(
    query_vector: list[float],
    book_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    client = get_client()

    flt = None
    if book_ids:
        flt = Filter(must=[FieldCondition(key="book_id", match=MatchAny(any=book_ids))])

    hits = client.search(
        collection_name=COLLECTION,
        query_vector=query_vector,
        query_filter=flt,
        limit=limit,
        with_payload=True,
    )
    return [
        {**h.payload, "score": h.score}
        for h in hits
    ]


def delete_book_vectors(book_id: str):
    client = get_client()
    client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="book_id", match=MatchAny(any=[book_id]))]
        ),
    )

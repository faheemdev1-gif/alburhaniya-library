"""
Meilisearch client — handles index creation, document upsert, and keyword search.
"""
from __future__ import annotations
import logging
import meilisearch
from app.core.config import get_settings

logger = logging.getLogger(__name__)

INDEX_NAME = "arabic_books"


def get_client() -> meilisearch.Client:
    s = get_settings()
    return meilisearch.Client(s.meili_url, s.meili_master_key)


def ensure_index():
    s = get_settings()
    client = get_client()
    try:
        client.get_index(INDEX_NAME)
    except Exception:
        logger.info("Creating Meilisearch index: %s", INDEX_NAME)
        task = client.create_index(INDEX_NAME, {"primaryKey": "id"})
        client.wait_for_task(task.task_uid)

    idx = client.index(INDEX_NAME)
    idx.update_settings({
        "searchableAttributes": ["text", "book_title"],
        "filterableAttributes": ["book_id", "book_title", "page_number", "volume"],
        "sortableAttributes": ["page_number"],
        "typoTolerance": {"enabled": True},
        # Allow a single query to return every matching chunk across the
        # whole library (default cap is 1000) so common words don't get
        # silently truncated before we group them into per-page results.
        "pagination": {"maxTotalHits": s.meili_max_total_hits},
    })
    logger.info("Meilisearch index configured ✓ (maxTotalHits=%d)", s.meili_max_total_hits)


def upsert_documents(docs: list[dict]):
    """docs: list of {id, book_id, book_title, page_number, chunk_index, text}"""
    client = get_client()
    idx = client.index(INDEX_NAME)
    # Small batches (50 docs) + 10 min timeout for very large Arabic books
    for i in range(0, len(docs), 50):
        task = idx.add_documents(docs[i: i + 50])
        client.wait_for_task(task.task_uid, timeout_in_ms=600_000)


def keyword_search(
    query: str,
    book_ids: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    client = get_client()
    idx = client.index(INDEX_NAME)

    params: dict = {
        "limit": limit,
        "attributesToHighlight": ["text"],
        "highlightPreTag": "<mark>",
        "highlightPostTag": "</mark>",
        "matchingStrategy": "all",
    }
    if book_ids:
        params["filter"] = " OR ".join(f'book_id = "{bid}"' for bid in book_ids)

    results = idx.search(query, params)
    return results.get("hits", [])


def delete_book(book_id: str):
    client = get_client()
    idx = client.index(INDEX_NAME)
    task = idx.delete_documents_by_filter(f'book_id = "{book_id}"')
    client.wait_for_task(task.task_uid, timeout_in_ms=300_000)

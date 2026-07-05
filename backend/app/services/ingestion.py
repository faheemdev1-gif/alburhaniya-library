"""
Ingestion pipeline.
Reads a document file, extracts text per page, chunks it,
normalises Arabic, then indexes into both Meilisearch and Qdrant.
"""
from __future__ import annotations
import hashlib
import json
import logging
from pathlib import Path

from app.core.arabic_utils import normalize_arabic, split_into_chunks
from app.core.config import get_settings
from app.core.parsers import parse_document
from app.services import keyword_search as kw, vector_search as vs
from app.services.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


def _book_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:16]


def ingest_book(path: Path, title: str | None = None) -> dict:
    """
    Ingest one book. Returns metadata dict.
    Idempotent — re-ingesting replaces existing data for that book.
    """
    s = get_settings()
    emb_svc = get_embedding_service(s.embedding_model)

    book_id = _book_id(path)
    book_title = title or path.stem
    logger.info("Ingesting '%s' (%s) …", book_title, path.suffix)

    # ── Parse ──────────────────────────────────────────────────────────────────
    pages = parse_document(path)
    if not pages:
        logger.warning("No text extracted from %s", path)
        return {"book_id": book_id, "title": book_title, "chunks": 0}

    # ── Chunk & normalise ──────────────────────────────────────────────────────
    meili_docs: list[dict] = []
    qdrant_points: list[dict] = []
    texts_to_embed: list[str] = []
    meta_buffer: list[dict]   = []

    for page in pages:
        norm_text = normalize_arabic(page.text)
        chunks = split_into_chunks(norm_text, s.chunk_size, s.chunk_overlap)

        for ci, chunk in enumerate(chunks):
            chunk_id = f"{book_id}_p{page.page_number}_c{ci}"
            meili_docs.append({
                "id":          chunk_id,
                "book_id":     book_id,
                "book_title":  book_title,
                "page_number": page.page_number,
                "page_label":  page.page_label or str(page.page_number),
                "volume":      page.volume,
                "chunk_index": ci,
                "text":        chunk,
            })
            texts_to_embed.append(chunk)
            meta_buffer.append({
                "chunk_id":    chunk_id,
                "book_id":     book_id,
                "book_title":  book_title,
                "page_number": page.page_number,
                "page_label":  page.page_label or str(page.page_number),
                "volume":      page.volume,
                "chunk_index": ci,
                "text":        chunk,
            })

    # ── Embed in batches ───────────────────────────────────────────────────────
    logger.info("  Embedding %d chunks …", len(texts_to_embed))
    vectors = emb_svc.embed(texts_to_embed)

    for meta, vec in zip(meta_buffer, vectors):
        qdrant_points.append({"chunk_id": meta["chunk_id"], "vector": vec, "payload": meta})

    # ── Delete old data for this book (idempotent re-index) ───────────────────
    try:
        kw.delete_book(book_id)
        vs.delete_book_vectors(book_id)
    except Exception:
        pass  # first-time ingest — nothing to delete

    # ── Push to indexes ────────────────────────────────────────────────────────
    logger.info("  Uploading to Meilisearch …")
    kw.upsert_documents(meili_docs)

    logger.info("  Uploading to Qdrant …")
    vs.upsert_vectors(qdrant_points)

    result = {
        "book_id":     book_id,
        "title":       book_title,
        "file":        str(path),
        "pages":       len(pages),
        "total_pages": len(pages),
        "chunks":      len(meili_docs),
    }
    logger.info("  Done ✓  %s", result)
    return result


def ingest_directory(books_dir: str) -> list[dict]:
    """Walk the books directory and ingest all supported files."""
    supported = {".pdf", ".docx", ".doc", ".html", ".htm", ".txt"}
    results = []
    for path in Path(books_dir).rglob("*"):
        if path.suffix.lower() in supported and path.is_file():
            try:
                meta = ingest_book(path)
                results.append(meta)
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", path, exc)
    return results

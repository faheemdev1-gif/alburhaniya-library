#!/usr/bin/env python3
"""Build deterministic semantic chunks and optional E5 embeddings.

Run after ``scripts/build_index.py``. Embeddings are generated only when the
corpus changes; the server memory-maps the resulting matrix at query time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date

import numpy as np


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

from app.services.semantic_chunks import split_semantic_chunks  # noqa: E402


DEFAULT_MODEL = os.environ.get("SEMANTIC_MODEL", "intfloat/multilingual-e5-base")
DB_PATH = os.environ.get("LIBRARY_DB_PATH", os.path.join(ROOT, "library.db"))
VECTORS_PATH = os.environ.get(
    "SEMANTIC_EMBEDDINGS_PATH", os.path.join(ROOT, "semantic_embeddings.npy")
)
MANIFEST_PATH = os.environ.get(
    "SEMANTIC_MANIFEST_PATH", os.path.join(ROOT, "semantic_manifest.json")
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS semantic_chunks (
    chunk_id       TEXT PRIMARY KEY,
    vector_index   INTEGER NOT NULL UNIQUE,
    book_id        TEXT NOT NULL,
    seq            INTEGER NOT NULL,
    printed_page   TEXT,
    citation_label TEXT,
    start_char     INTEGER NOT NULL,
    end_char       INTEGER NOT NULL,
    text           TEXT NOT NULL,
    qasida_number  INTEGER,
    qasida_title   TEXT,
    bayt_from      INTEGER,
    bayt_to        INTEGER,
    source_tier    INTEGER NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(book_id)
);
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_page
    ON semantic_chunks(book_id, seq, start_char);
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_qasida
    ON semantic_chunks(book_id, qasida_number, bayt_from);
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_tier
    ON semantic_chunks(source_tier);
"""


def build_chunk_metadata(conn: sqlite3.Connection) -> tuple[list[str], str]:
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM semantic_chunks")
    rows = conn.execute(
        """SELECT p.book_id, p.seq, p.printed_page, p.citation_label,
                  p.qasida_number, p.qasida_title, p.bayt_from, p.bayt_to,
                  p.text, b.source_tier
             FROM pages p JOIN books b ON b.book_id = p.book_id
            ORDER BY p.book_id, p.seq"""
    ).fetchall()

    corpus_hash = hashlib.sha256()
    chunk_texts: list[str] = []
    inserts = []
    vector_index = 0
    for row in rows:
        page_text = row[8]
        corpus_hash.update(row[0].encode("utf-8"))
        corpus_hash.update(str(row[1]).encode("ascii"))
        corpus_hash.update(page_text.encode("utf-8"))
        for chunk in split_semantic_chunks(page_text):
            chunk_id = f"{row[0]}-p{row[1]}-c{chunk.start_char}"
            inserts.append((
                chunk_id, vector_index, row[0], row[1], row[2], row[3],
                chunk.start_char, chunk.end_char, chunk.text,
                row[4], row[5], row[6], row[7], row[9],
            ))
            chunk_texts.append(chunk.text)
            vector_index += 1

    conn.executemany(
        """INSERT INTO semantic_chunks (
               chunk_id, vector_index, book_id, seq, printed_page,
               citation_label, start_char, end_char, text, qasida_number,
               qasida_title, bayt_from, bayt_to, source_tier
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        inserts,
    )
    conn.commit()
    return chunk_texts, corpus_hash.hexdigest()


def _atomic_save_vectors(path: str, vectors: np.ndarray) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".npy", delete=False) as tmp:
        temp_path = tmp.name
    try:
        np.save(temp_path, vectors)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _atomic_write_json(path: str, payload: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=directory, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def build(*, model_name: str, batch_size: int, metadata_only: bool = False) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        chunk_texts, corpus_hash = build_chunk_metadata(conn)
    finally:
        conn.close()

    manifest = {
        "model": model_name,
        "dimensions": None,
        "corpus_version": f"{date.today().isoformat()}-{corpus_hash[:12]}",
        "corpus_sha256": corpus_hash,
        "chunk_count": len(chunk_texts),
        "normalized": True,
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
    }
    if metadata_only:
        print(f"Built metadata for {len(chunk_texts)} semantic chunks")
        return manifest

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    prompts = getattr(model, "prompts", {}) or {}
    documents = chunk_texts if any(
        name in prompts for name in ("document", "passage", "corpus")
    ) else [f"passage: {text}" for text in chunk_texts]
    vectors = model.encode_document(
        documents,
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype(np.float32, copy=False)
    manifest["dimensions"] = int(vectors.shape[1])
    _atomic_save_vectors(VECTORS_PATH, vectors)
    _atomic_write_json(MANIFEST_PATH, manifest)
    print(
        f"Built {len(chunk_texts)} embeddings ({vectors.shape[1]} dimensions) "
        f"with {model_name}"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="Build/check SQLite chunks without loading an embedding model.",
    )
    args = parser.parse_args()
    build(
        model_name=args.model,
        batch_size=max(1, args.batch_size),
        metadata_only=args.metadata_only,
    )


if __name__ == "__main__":
    main()

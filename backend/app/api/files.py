"""
Legacy: streamed original PDF/DOCX files for the PDF.js viewer under the
old ingestion pipeline. The default SQLite-FTS5 deployment stores parsed
page text only (no original binary files), since the shamela .htm exports
are the source of truth and are already split into per-page plain text.

Kept as a stub (rather than removed) so re-enabling the legacy Meilisearch
ingestion pipeline (ENABLE_LEGACY_MEILISEARCH=true) can restore this route
without other code changes.
"""
from fastapi import APIRouter, HTTPException
from app.core.config import get_settings

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{book_id}")
def serve_book_file(book_id: str):
    s = get_settings()
    if not s.enable_legacy_meilisearch:
        raise HTTPException(
            501,
            "Original file serving is unavailable in this deployment — books "
            "are stored as parsed page text (see /books/{book_id}/page/{seq} "
            "or /read/{book_id}/{seq}).",
        )
    from pathlib import Path
    from fastapi.responses import FileResponse
    from app.api.books_legacy_registry import load_registry  # legacy helper

    reg = load_registry()
    if book_id not in reg:
        raise HTTPException(404, "Book not found")
    file_path = Path(reg[book_id]["file"])
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf" if file_path.suffix.lower() == ".pdf" else "application/octet-stream",
        filename=file_path.name,
        headers={"Accept-Ranges": "bytes"},
    )

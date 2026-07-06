"""
MCP (Model Context Protocol) server for the Burhaniya library.

This gives Claude a real *tool* to search the library, instead of a URL
it has to construct and fetch on its own — an MCP tool call gives Claude
structured, validated access to search_library() and list_books()
directly, rather than guessing at a REST URL shape.

Runs as its own small ASGI app, in the same Docker image as the main
FastAPI app (app/main.py), reusing the same baked-in library.db and the
same search() function — just exposed a different way. It's mounted
inside app/main.py at "/mcp", so streamable_http_path is set to "/" here
(instead of leaving it at its default of "/mcp") to avoid a doubled
"/mcp/mcp" path once mounted.

Local run:      uvicorn app.mcp_server:app --host 0.0.0.0 --port 8001
Deployed:       mounted inside the main FastAPI app, see app/main.py
Claude side:    add this service's URL + "/mcp" as a custom connector
                (Settings -> Connectors -> Add custom connector).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.services import library_db as db

mcp = FastMCP(
    "burhaniya-library",
    instructions=(
        "Search the Burhaniya Arabic book library for an exact word or "
        "phrase. Use search_library for any request to look something up "
        "in this library. Results include the book title, the page it "
        "was found on, how many times the word occurs on that page, a "
        "highlighted snippet, and a URL to read the full page."
    ),
    stateless_http=True,
    # Serve at root internally — app/main.py mounts this whole app at
    # "/mcp", so leaving the default "/mcp" here would produce "/mcp/mcp".
    streamable_http_path="/",
)


@mcp.tool()
def search_library(query: str, limit: int = 50) -> dict:
    """Search the Arabic library for an exact word or phrase.

    Args:
        query: The Arabic word or phrase to search for (e.g. "الحب").
        limit: Maximum number of matching pages to return (default 50,
            capped at 500).
    """
    limit = max(1, min(limit, 500))
    results = db.search(query, limit=limit)
    return {"query": query, "total": len(results), "results": results}


@mcp.tool()
def list_books() -> dict:
    """List every book in the library (id, title, page count)."""
    return {"books": db.list_books()}


# Streamable-HTTP ASGI app. When run standalone (uvicorn app.mcp_server:app)
# this serves at "/" per streamable_http_path above. When mounted inside
# app/main.py at "/mcp", the combined external path is a clean "/mcp".
app = mcp.streamable_http_app()
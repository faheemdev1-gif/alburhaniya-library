# MCP token optimization

The MCP interface now uses compact, staged retrieval:

1. `list_books()` returns the catalogue without the long grade legend.
   Use `list_books(include_legend=true)` only when the definitions are needed.
2. `search_library()` defaults to 10 results and returns a short highlighted
   snippet rather than returning every matching page twice.
3. Use `get_page(book_id, seq)` to fetch the full text of a selected result.
4. Continue a search with `next_offset`.

## Search filters

`search_library` supports:

- `book_ids`: restrict results to selected books
- `source_code`: `primary` or `secondary`
- `page_from` / `page_to`: inclusive page-sequence range
- `context_chars`: 40–500 characters on each side of the match
- `limit`: 1–50 results per call
- `offset`: pagination cursor

The existing REST JSON endpoints retain their legacy full-text fields for
frontend compatibility. Compact retrieval is the MCP default.

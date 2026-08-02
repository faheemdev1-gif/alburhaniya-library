# MCP token optimization

The MCP interface now uses compact, staged retrieval:

1. `list_books()` returns the catalogue without the long grade legend.
   Use `list_books(include_legend=true)` only when the definitions are needed.
2. `search_library()` defaults to 8 results and 120 characters of context.
   Its default `compact` mode deduplicates book metadata and removes aliases,
   null filters, repeated provenance prose, and repeated source labels.
3. Set `mode="standard"` on search/page calls only for the previous verbose
   response contract.
4. Use `get_page(book_id, seq)` to fetch only selected full text.
5. Continue a search with `next_offset`.
6. `read_book()` now defaults to 8 pages / 12,000 characters; callers can
   explicitly request up to the former 25-page / 40,000-character limits.

## Claude compatibility

The same public `/mcp` endpoint uses stateless Streamable HTTP, supported by
Claude custom connectors, Claude Code, the Claude API MCP connector, and
ChatGPT connectors. Claude and ChatGPT web origins are accepted while DNS
rebinding protection remains enabled.

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

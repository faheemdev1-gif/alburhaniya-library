# Burhaniya Books MCP setup

The public endpoint is:

`https://burhaniya-library-backend.onrender.com/mcp`

It uses stateless Streamable HTTP. No separate Claude backend is required.

## Claude web / desktop custom connector

Add a custom Web connector and paste the endpoint above. Claude connects to
remote connectors from Anthropic's cloud, so the Render service must remain
publicly reachable.

## Claude Code

```bash
claude mcp add --transport http burhaniya-books \
  https://burhaniya-library-backend.onrender.com/mcp
```

Project-scoped `.mcp.json` alternative:

```json
{
  "mcpServers": {
    "burhaniya-books": {
      "type": "http",
      "url": "https://burhaniya-library-backend.onrender.com/mcp"
    }
  }
}
```

## Recommended model workflow

1. Call `search_library` using its default compact mode.
2. Narrow with `book_ids`, `source_code`, or page range when appropriate.
3. Call `get_page` only for results actually needed for the answer.
4. Follow `next_offset` only when the first result page is insufficient.
5. Use `read_book` for sequential reading, not ordinary search questions.

Use `mode="standard"` only for clients that depend on the previous verbose
search or page response.

## Source handling

- `primary`: authoritative shaykh material.
- `secondary`: supporting commentary or compilation.
- Never attribute a secondary interpretation directly to a shaykh.
- Book `b35` contains multiple speakers; verify the speaker before attribution.

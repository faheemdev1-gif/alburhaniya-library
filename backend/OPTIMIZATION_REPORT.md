# Burhaniya Books connector optimization report

## Version 2.1.0

The Arabic database, page text, book identifiers, printed-page references,
and source classifications were not modified.

### Changes

- Default search size reduced from 10 hits / 160 context characters to
  8 hits / 120 context characters.
- Book title and source metadata are emitted once per book rather than once
  per hit.
- Removed redundant search aliases, null filter echoes, count breakdowns,
  and repeated provenance prose from compact mode.
- Added `mode="standard"` for backward compatibility.
- Compact page reads omit duplicated navigation and bilingual grade fields.
- Sequential reading defaults reduced from 25 pages / 40,000 characters to
  8 pages / 12,000 characters, with the former maxima still available by
  explicit request.
- Shortened server and tool instructions to reduce tool-definition overhead.
- Retained stateless Streamable HTTP and added Claude/ChatGPT web origins to
  the transport security policy.
- Added Claude web, Claude Desktop, Claude Code, and `.mcp.json` setup notes.

### Measured search payloads

Measured as compact UTF-8 JSON characters against the previously optimized
default contract:

| Query | Previous | v2.1 compact | Reduction |
| --- | ---: | ---: | ---: |
| الله | 5,290 | 2,588 | 51.1% |
| القلب | 5,685 | 2,795 | 50.8% |
| المحبة | 5,675 | 2,748 | 51.6% |

This is an additional reduction on top of the earlier 84–86% reduction from
the original backend. The approximate cumulative reduction for default search
responses is therefore 92–93%, depending on query and result composition.

### Validation

- 7/7 retrieval and compact-contract tests pass.
- All Python source files compile successfully.
- Exact Arabic search, filters, pagination, legacy full text, and page ranges
  remain covered by tests.
- Transport configuration follows the public Streamable HTTP endpoint model
  used by Claude and ChatGPT connectors.

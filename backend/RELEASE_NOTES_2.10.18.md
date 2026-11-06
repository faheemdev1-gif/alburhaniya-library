# Burhaniya connector 2.10.18 — run-2 report fixes

Tool contract 15.1; the same five research tools remain available.

## Changes

- Metadata tools return a small summary by default. Request `detail="full"` for the complete live connector/corpus contract and printed-label diagnostics. `projection="full"` selects complete book metadata without implicitly selecting all server diagnostics.
- Page and passage tools also accept `detail="full"`. Routine passages retain exact offsets and text versions without duplicating the passage in `source_span.source_quote`. Detailed replies retain the quote and full timing/digests.
- Default auto search unions attested hamza spellings for short phrases. The response labels these as `spelling_discovery`, identifies original and source forms, and retains spelling-sensitive literal censuses. Explicit `match_mode="exact"` preserves the existing research contract. Expansion is bounded to 128 attested phrase forms; longer/larger requests retain the normal cascade.
- English function words no longer drive term relevance. Highlight matching uses Unicode word boundaries. Requested context surrounds the actual evidence span; apostrophes and quotation marks remain readable, while HTML delimiters stay escaped.
- Completed counted searches use the corpus-bound result cache. An explicitly requested completeness audit bypasses it so the candidate stage is inspected afresh. Lexeme census counting no longer performs another full ranked search. Vocabulary lookup uses indexed subsets instead of loading all 120,275 spellings. Pure source transformations are cached by source text and navigation scope. Ranking runs before expensive attribution/structural enrichment.
- Census cache keys include the operation, preventing a page-identity set from colliding with a count response.
- Invalid selectors/arguments are recorded as `client_error`, separately from server failures. Unknown-book errors list valid IDs; invalid-page errors give the book's valid page range. Non-search errors omit search retry/intent fields.
- The ambiguous root form `فان` is no longer taken as evidence for `فني`; this prevents `فإنّ` from manufacturing annihilation parallels. Returned parallel candidates include the actual source/candidate words supporting every claimed root. They remain unverified discovery candidates.
- Footnote evidence blocks agree with the explicit separator used by content classification and search exclusion.
- Source corruption recorded by the supplied report is flagged for scan review. Source quotations and ambiguous printed labels are preserved.
- The search-tool description groups basic and advanced controls. Readable compact responses are the default; advanced ultra-compact clients can obtain the decoder through `list_books(detail="full")`. Token measurements include that extra decoder call.
- The launcher defaults to one HTTP worker, avoiding duplicate eager language-pattern compilation during startup on small VPS instances. Shared source-pattern clitics are factored to reduce compilation work. `WEB_CONCURRENCY` can still select 1–8 workers.
- `deploy/compose.state.yml` supplies a named Docker volume for monitoring and cache continuity.

## Deployment

This package contains the complete backend source and source corpus. `library.db` is intentionally rebuilt by the existing Dockerfile, as in previous releases. Old semantic artifacts are retained but are not enabled automatically.

1. Back up the current backend directory and configuration. Replace the backend files with this directory. Preserve deployment secrets and the parent Compose/Caddy configuration.
2. From the repository root, rebuild using the existing Compose configuration:

   `sudo docker compose up -d --build --no-deps backend`

3. To enable durable monitoring/cache storage, add the supplied override last in the existing Compose file list. For the setup with both existing files:

   `sudo docker compose -f docker-compose.yml -f docker-compose.override.yml -f backend/deploy/compose.state.yml up -d --build --no-deps backend`

   If there is no `docker-compose.override.yml`, omit that argument. The named volume must be retained; `docker compose down -v` deletes it. Prior ephemeral history cannot be recovered.

4. Check `/health`, refresh the MCP connection if its schema is cached, and verify `get_book("b14")` reports server 2.10.18 / contract 15.1. Repeat the report's tests against the deployed service.

The package is locally tested; deploying it to the OVH server is a separate step. Nothing in this archive changes a running server by itself.

## Remaining acceptance work

No 10/10 production or retrieval rating is claimed.

- Missing Quran verse references and the duplicated verse in b39 page 248 require the original source scan and editorial verification.
- Repeated printed labels need source-by-source scan review. Sequence-based citations continue to avoid presenting unreliable printed labels as certain.
- First uncached lexeme censuses still require performance measurement on the target VPS; warm-cache improvements do not establish a cold-request latency guarantee.
- Article-based homograph errors and general question-answer relevance need independently graded Arabic passages. Returning fewer than five defensible results is not repaired by padding results.
- Semantic retrieval requires a matching rebuilt index and the E5 query-model dependency/weights. The supplied old vector files are not evidence that this path is ready. Semantic availability alone is not a relevance score.
- A 7-day reliability score requires 7 days of deployed observations on persistent storage.
- The existing independent retrieval-rating script requires a separately graded private set. Tests are engineering evidence, not an automatic religious-answer relevance rating.

See `verification/2.10.18/` for local validation results.

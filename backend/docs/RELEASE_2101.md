# Al Burhaniya 2.10.1 source patch

This release corrects problems reproduced against deployed 2.10.0. The public
MCP interface remains five tools, contract 12.0. Deploy the new source using
the existing Dockerfile or rebuild `library.db` and run `scripts/start_server.py`.
The generated database is intentionally absent from the archive.

## Corrections

- Comparison questions of the form "ما الفرق بين X وY؟" now retain X and Y as
  distinct required evidence terms. The natural-language query for `التوكل`
  versus `التواكل` retrieves `b10-p20` first, rather than unrelated passages
  about relief. The interrogative `ما` is no longer marked as negation.
- Question anchoring no longer judges word commonness through speculative
  morphological variants such as the unrelated pronoun `هم` for `بالهم`.
- An introduction merely *about* disciple etiquette is downranked against
  guidance containing concrete conduct, such as `b37-p57` and `b07-p119`.
- `literal_matching_pages` and `literal_occurrences` count exact source
  surfaces. `normalized_matching_pages` and `normalized_occurrences` retain
  the safe article-aware census. `retrieval_hit_count` still describes
  retrieval candidates, which may include article variants and disclose them
  in `matched_terms`. For `التوبة`, the scoped `b12-p60` case now reports
  literal zero and normalized two.
- Paragraph mode stops after at most three neighboring pages, and declares a
  cap and continuation locator if a source has no useful paragraph boundary.
- The `b37` note now identifies the compiler named in metadata without
  presenting documentary authenticity as established.
- The local MCP verification compares the intentionally compact catalogue
  contract with the corresponding subset of `/health`.

## Verification and limits

Rebuild from all 43 books, then run `python -m pytest -q`,
`python scripts/independent_corpus_audit.py library.db`, and
`python scripts/verify_http_local.py`. The last check starts a local server
and exercises all five tools over MCP HTTP.

The public 30-question replay is a development fixture with reference pages,
not an independent answer-quality assessment. It currently locates a reference
page for 26/30, with four missed references all pointing to `b44-p40`.
Several returned passages on those questions remain indirect. The held-out
human relevance audit, deployed 2.10.1 acceptance, seven-day monitoring, and
original-scan provenance review remain outstanding. Do not label this release
9+/10 based on local tests, nonempty results, or the public fixture alone.

The prior live deployment showed network/connector overhead of several
seconds even when a backend cache hit took under 2 ms. This package improves
local comparison-query processing; it does not demonstrate a fix for external
transport latency. Re-measure that separately after deployment.

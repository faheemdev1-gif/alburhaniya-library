# Al Burhaniya 2.10.2 source patch

## Implemented

- A common source-offset attribution guard now appears in literal and question
  search, bounded and paragraph `get_passage`, and the full-page guard list.
  Both `b07-p256-c1421` and `b07-p256-c1474` retain the reported-view warning.
  The guard records an explicit source marker and remains unreviewed; no author
  position is inferred from a reported quotation.
- Comparison parsing recognises more `الفرق/التوازن/يفرق/يجمع بين X وY` frames
  and the `معنى X وكيف يختلف عن Y` frame. Both concepts remain required in
  local comparison evidence. A role word such as `الشيخ` or an isolated
  `الصالحين` no longer triggers an unrelated two-concept routing rule.
  Corpus-attested smoking vocabulary bridges formal and colloquial discovery;
  literal counts remain based on the original query. Weak mentions stay
  labelled `topic_only` when no ruling is supported. This is candidate
  discovery, not answer grading.
- The result cache is shared by local workers through SQLite, bounded to 512
  entries, and keyed by server version, corpus identity and full request
  controls. Incomplete responses are not cached. A read-only cache path falls
  back to the process cache.
- Duplicate locations use `also_in`; the same list is no longer repeated as
  `alternate_locations`. Attribution of an alternate location is retained on
  that location. The server reports 2.10.2 and continues contract 12.0.

## Acceptance boundary

The final local public replay returned results for 30/30 historical questions
and located a listed reference page for 27/30 (up from 26/30 in 2.10.1).
This measures reference presence, not whether the displayed evidence directly
answers the question. The independent corpus audit and isolated MCP HTTP
check passed. See the release verification files for details.

Local tests and public reference-page replays cannot certify retrieval quality
or a 9+ score. The owner-held private set, Arabic source review, relevance
grading, client schema refresh, deployed client latency and 24-hour/1,000
attempt monitoring window specified in the roadmap require deployment and
independent observers. Documentary review and repeated printed-label scan
checks also remain open. Do not mark these complete based on source changes.

Rebuild `library.db` with `scripts/build_index.py`; run `python -m pytest -q`,
`python scripts/independent_corpus_audit.py library.db`, and
`python scripts/verify_http_local.py`. The database is generated and excluded
from the release archive.

# Local semantic retrieval

The production search path now supports a local multilingual E5 index without
Qdrant, Meilisearch, a hosted embedding API, or persistent disk.

## Build

```bash
python scripts/build_index.py
python scripts/build_semantic_index.py
```

`build_semantic_index.py --metadata-only` validates deterministic chunking
without downloading or loading the embedding model. The full build writes:

- `semantic_chunks` metadata in `library.db`
- `semantic_embeddings.npy` (normalized float32 vectors)
- `semantic_manifest.json` (model, dimensions and corpus checksum)

The Docker build runs both indexing steps. Set `SEMANTIC_MODEL` to test another
Sentence Transformers model without changing code.

## Runtime behavior

- The five MCP tools are unchanged.
- If semantic artifacts exist, `auto` unions exact, terms, single-word lexeme
  and semantic candidates, then reranks them.
- If artifacts are absent or `ENABLE_LOCAL_SEMANTIC_SEARCH=false`, the old
  exact → terms → lexical-hybrid cascade remains active.
- Semantic-only hits always contain `match_type=semantic`, `semantic_score`,
  `citation_verified=false`, and `verification_required=true`.
- A lexical match on the same page remains citation-verified and keeps its
  lexical match type.
- Book, source, page and qasida filters are applied before vector top-k.

## Evaluation

```bash
python scripts/evaluate_semantic_search.py
```

The included 30-query set is an exact-preservation baseline anchored to stable
chunk IDs. Add separately reviewed paraphrase and hard-negative cases before
using the metrics to choose a production semantic threshold. The evaluator
reports Recall@5, Precision@5, MRR, primary-source presence, incorrect-topic
rate and semantic-only false positives.

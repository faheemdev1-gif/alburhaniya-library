# Al Burhania Library Connector 2.7.0

Updated source project based on the supplied 2.6.0 ZIP and two September assessments.
MCP tool contract: **9.0** (`alburhaniya-tools-v9`). Exactly five tools remain.

## Start locally

Use Python 3.11 (Docker target) or 3.12. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/build_index.py
python -m pytest -q
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health: `http://localhost:8000/health`; connector: `http://localhost:8000/mcp/`.
The database is generated, not missing source. `build_index.py` replaces the
configured `library.db`: stop the server and preserve any custom database first.
The corpus rebuilds to 43 books, 6,935 pages, 95 qasidas and 2,682 bayts.

## Docker / Render

```bash
docker build -t alburhaniya:2.7.0 .
docker run --rm -p 8000:8000 alburhaniya:2.7.0
```

The image installs `requirements-core.txt`, rebuilds the database and runs the
classified unittest release suite during build. A failed hard or retrieval-quality
gate stops the build. `requirements.txt` retains the original extended optional
ingestion/embedding stack; it is no longer required for the default lexical service.
Do not enable legacy external engines without their services and dependencies.

After deploying, refresh connector discovery / `tools/list` in every client.
Paragraph controls already existed in 2.6.0; stale clients must refresh their schema.
See [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) and
[docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

## Changes

- Question discovery excludes interrogatives/pronouns from intent evidence and
  ranks source-local relationship clues. The livelihood fixture has a declared,
  versioned expansion policy; it is not a general semantic understanding claim.
- Repeated immutable text/pattern computations are cached with bounded caches.
  Exact and lexeme source identities are preserved in the comparison benchmarks.
- `check_completeness=true` audits actual lexical candidates without requiring
  counts. `include_counts=true` also enables it. The response explicitly reports
  `not_checked`, `not_supported`, `ok`, or `warning`.
- `list_books(projection="ids")` reduces catalogue cost;
  `projection="full", book_ids=[...]` batches complete book provenance.
- Boolean metadata is consistent; conflicting passage selectors and oversized
  passage batches fail explicitly instead of silently selecting/truncating.
- Semantic activation checks corpus compatibility before using vectors.

Exact wording in a passage is not proof that it answers a question. Reformulated
results declare `answer_verified=false`, local intent evidence, and a warning.
Do not turn an author's discussion or rejection of a practice into advice.

## Verification

```bash
python scripts/run_regression_suite.py
python scripts/independent_corpus_audit.py library.db
python scripts/prove_audit_failure.py
python scripts/verify_assessment_release.py --runs 7 --output verification/assessment_release.json
python scripts/verify_release_270.py --runs 7
python scripts/verify_http_local.py
```

The last script requires `requirements-dev.txt`. It measures seven samples per
scenario through a fresh local MCP subprocess, separates server/client timing,
records retries, and counts structured and complete MCP result tokens using
`cl100k_base`. Counts are not an invoice or actual client context consumption.
See the generated JSON and test outputs in `verification/`.

## Research and provenance review

`data/research_questions.json` contains **40 proposed questions**, split into 24
development and 16 held-out questions. None has been passed off as human-reviewed.
`verification/development_review.json` contains passages for the 24 development
questions, ready for independent grading. The held-out queries were not executed
or used to tune this update.

```bash
python scripts/evaluate_questions.py --split development --output verification/development_review.json
# Only after tuning is frozen, export the held-out set for an independent reviewer:
python scripts/evaluate_questions.py --split held_out --output verification/held_out_review.json
python scripts/evaluate_questions.py --score-review verification/held_out_review.json
python scripts/review_provenance.py
```

The scorer rejects pending/unlabelled reviews. Supply reviewer identity, grade
0/1/2, and a source-based note for every returned candidate. Missing results count
as not relevant. Keep the held-out results separate from further tuning.

`data/provenance_review.json` is an automated triage inventory of all 43 records,
including dated review basis, text hashes, and bounded front/back-matter clues.
It preserves all author/compiler assignments. Its broad triage flags **33**
records (including default `needs_review` values); this differs from the reports'
15-record narrower finding and is not a count of proven misattributions.
Original title pages, colophons or documented transmission evidence are needed
before upgrading unresolved attribution.

## Optional semantic search

Keep `ENABLE_LOCAL_SEMANTIC_SEARCH=false` for this release. The supplied vectors
contain 29,124 chunks, while the current corpus yields 29,128. Their corpus hashes
also differ. They are preserved in this archive but excluded from the default
Docker image. **Do not enable the old vectors or edit their manifest to hide the
mismatch.** Regenerate metadata and vectors together with the optional model stack,
then independently test retrieval quality before enabling them:

```bash
python -m pip install -r requirements.txt
python scripts/build_semantic_index.py
```

For a semantic Docker deployment, install the optional requirements and build/copy
the regenerated matching artifacts into a separate image. The default image is
intentionally lexical. Rebuild/restart workers when corpus or index artifacts change.

## Limits

This project has not been deployed to your live server. Local evidence is not a
production latency/SLA result. Documentary attribution and human relevance review
remain open. No 9+ score is claimed; the external weighted score must be assigned
after the release is deployed and independently reassessed.

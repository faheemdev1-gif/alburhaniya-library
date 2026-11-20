# Al Burhaniya Books 2.10.19

This release retains contract 15.1 and the five research tools. The live server answered as 2.10.18 during review.

## OVH deployment

From the parent project, use your existing Compose files and preserve your environment, Caddy configuration and data volumes. To include semantic retrieval, build the backend with the E5 option and start that image.

```sh
sudo docker compose build --build-arg WITH_E5=1 backend
sudo docker compose up -d --no-build --no-deps backend
```

For durable monitor history include the existing backend/deploy/compose.state.yml override in your Compose file list. Keep one worker initially. The semantic build downloads approximately 1.1 GB of model weights and uses more memory than the lexical build. The default WITH_E5=0 retains the lightweight deployment. After starting, check /health and get_book(detail="full") for 2.10.19 and semantic_active. Local release testing covered the Python services and HTTP MCP calls. A Docker image build and deployment on OVH remain to be verified.

## Engineering changes and local results

- The public question replay found a listed reference page in the first five hits on 18 of 18 known questions. The local 2.10.18 baseline reached 17 of 18, including one partial request. For the sincere-disciple question, 2.10.19 ranked b07 sequence 138 first. The live 2.10.18 connector also found that passage on a separate request.
- Ranking recognises a sign explicitly attached to a source expression for the subject. Wrong-sense exclusions now apply to the queried concept and the relevant text span. Repeated printed labels use a sequence citation across result types. Results for flagged passages inherit the page's editorial warning.
- Single-query counts reuse eligible rows and occurrence spans. Lexeme explanations are constructed for displayed results after ranking. Three paired local cold-process runs reproduced 1,329 expanded pages, 636 literal pages and 1,063 literal occurrences for ذكر on both versions. Candidate times ranged from 0.82 to 2.55 seconds with other work running. OVH cold latency remains unmeasured.
- The supplied vector file was truncated. The repair used the original August database with the verified corpus fingerprint, matched unchanged chunk text and re-encoded 1,026 missing or changed vectors using the pinned multilingual E5 model. The packaged matrix covers 29,128 chunks. The build verifies its checksum and the corpus fingerprint. Semantic retrieval excludes footnote chunks and requires explicit inclusion for navigation chunks.
- The scheduled monitor preserves concurrent observations and distinguishes calls that failed from calls that could not start during an outage. Daily summaries report both attempted and scheduled success rates.
- The local corpus audit passed across 43 books, 6,935 pages, 95 qasidas and 2,682 bayts. The HTTP SDK passed 18 smoke checks and eight concurrent requests completed without client errors. All ten existing token-budget checks passed.

## Outstanding evidence

The 6 November weighted expert estimate was 8.68/10. The public questions exercise known cases. An overall score above nine requires independent Arabic judgments on unseen questions and production observations. The scan review for b39 sequence 248 and ambiguous printed labels remains open. The source wording is preserved.

The final suite passed 373 tests and 41 subtests. On the separate 30-query semantic-only phrase benchmark, 21/30 queries returned the annotated chunk in the first five positions. The full per-query output is in verification/2.10.19/semantic_benchmark.json.

# Local verification — 2.10.18

- All five MCP tools discovered and executed through the actual HTTP SDK: 18 smoke checks passed.
- Eight concurrent HTTP searches completed fully without errors; slowest client call 4,869 ms.
- Run-2 report regressions: 11 passed.
- Historical suite with three isolated test workers: 368 passed; one cold comparison query reached the 18-second budget. Its complete four-test module then passed serially in 3.98 seconds. The budget observation remains recorded, not relabelled as a pass.
- Ten corrected regression checks and the separate startup/shutdown checks passed.
- Independent corpus audit: pass (43 books, 6,935 pages, 95 qasidas, 2,682 bayts).
- Token-budget gate: all 10 controls passed, with decoder-fetch cost accounted for.
- Pinned production dependency lock installed successfully. A Docker image was not built here.

## Spot measurements

| Check | Local result |
| --- | ---: |
| One-book default JSON | 1,247 characters |
| Two complete book records with summary diagnostics | 2,764 characters |
| First uncached lexeme census | 1,553 ms |
| Repeated lexeme census | 1.9 ms |

These are local measurements, not hardware-matched before/after latency comparisons. Literal counts preserve spelling; expanded retrieval counts describe a different evidence relation.

## Acceptance boundary

No 10/10 rating is assigned. Cold count latency is still above one second, and a parallel regression exposed a budget limit. Original scans are required for damaged verse references, a duplicated verse, and repeated printed-page labels. Semantic search still needs a rebuilt matching index and installed model weights. General question relevance needs independent Arabic judgments. Production reliability needs deployment plus seven days of retained observations.

Deployment instructions and the full change list are in `RELEASE_NOTES_2.10.18.md`. Machine-readable results, test logs, and the earlier iteration are in `verification/2.10.18/`.

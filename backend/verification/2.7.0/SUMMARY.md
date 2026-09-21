# Verification summary - 2.7.0

- Clean virtual environment installed successfully from `requirements-dev.txt`.
- Python 3.12.14: **155 tests passed, zero failures, zero skips**.
- One upstream Starlette/AnyIO deprecation warning remains; it is not a failed test.
- Classified hard/quality gate suite: pass.
- Frozen literal corpus fixtures: **36/36 pass**.
- Corpus structure audit: pass (43 books, 6,935 pages, 95 qasidas, 2,682 bayts).
- Deliberately corrupted stable-ID negative control: detected correctly.
- Actual missing retrieval candidates and equal-count substitutions: detected.
- Fresh MCP stdio discovery, schema and repeated-call checks: pass.
- Existing production regression suite against an isolated **local HTTP** server: pass.
- Clean pinned-dependency corpus rebuild: 43 books, 6,935 pages and 1,726,697 tokens.
- Four fixed direct-call comparisons preserve the baseline result IDs; median
  reductions in the final run range from about **55% to 92%**. Hardware/load and
  cold-versus-warm effects apply; this is not a production SLA.
- IDs-only catalogue: roughly 65% fewer structured tokens than the compact
  catalogue in this measured `cl100k_base` workflow. Full provenance and response
  wrapper costs are separately measured in `release_270.json`.
- Incompatible supplied semantic artifacts detected: keep disabled until rebuilt.
- All mapped source texts and source metadata preserved; see `project_inventory.json`.

## Not claimed

No live deployment, Docker-engine run, full embedding-model validation, independently
reviewed 40-question accuracy score, completed documentary provenance certification,
or external weighted score above 9. The project includes instructions and review
materials for those remaining checks.

Machine-readable reports and exact logs are included beside this summary.

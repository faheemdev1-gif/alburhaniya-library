# Release 2.8.0 checklist

## Automated local gates

1. Rebuild with `python scripts/build_index.py` while the service is stopped.
2. Run `python scripts/finalize_verification.py` and require every exit code to be zero.
3. Inspect `verification/audit_replay_280.json`: reference-page presence is a
   development regression measure, not a direct-answer accuracy score.
4. Verify archive integrity and unchanged original source hashes with
   `scripts/package_release.py`.

## Required after deployment

1. Preserve the previous deployed commit/image and environment for rollback.
2. Build and deploy through the existing hosting account.
3. Confirm `/health` reports server 2.8.0, contract 10.0, five tools and an intact corpus.
4. Run `scripts/production_mcp_regression.py --endpoint https://YOUR-HOST/mcp/`.
5. In every supported client, refresh discovery and verify `include_toc`,
   `include_topic_only`, `check_completeness`, catalogue `projection`/`book_ids`,
   and passage `context_mode`/`max_chars` are callable.
6. Check both a fresh client and a client that was open before deployment.
   A server-side schema check does not establish plugin-wrapper refresh.
7. Replay the supplied audit, read the returned source passages, and grade results.
8. Measure repeated production HTTP latency with documented load/cache conditions.

## Independent acceptance gates still open

- An independent reviewer must preregister reference passages and grade a
  genuinely held-out, diverse question set. The known-audit test is development
  evidence. Do not claim the report's 80% held-out target or an above-9 score from it.
- Authenticate the 15 unresolved catalogue attributions with title pages,
  colophons, official catalogues or documented transmission evidence.
- Resolve repeated anthology pagination against original scans. Sequence-qualified
  citations are now unique, but the printed pagination's original cause is unverified.
- Optional vector retrieval requires a compatible rebuilt index and separate evaluation.

Rollback: redeploy the preserved previous image/commit through the normal host.
Do not mix old semantic vectors with a changed corpus/index.

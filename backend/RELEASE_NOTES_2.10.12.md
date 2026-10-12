# Al Burhaniya Connector 2.10.12 — audit repair

This release addresses the 12 October 2026 2.10.11 audit. It preserves the supplied book texts and rebuilds the index from them. The tool contract is 13.0 because the misleading `retrieval_completeness.literal_pages` field was renamed to `normalized_pages` and heading paragraph semantics changed. Refresh tools/list in every client after deployment.

## Reproduced and repaired

- `ما صفات المريد الصادق` now searches the attested subject phrase; b07 p138 and b16 p37 are in the first five. Generic role nouns remain when part of an attested compound.
- Attested discovery aliases connect خشية/خوف, أمل/رجاء, محبة/حب, محمد/النبي/الرسول and several other terms. The fresh fear/hope wording finds b37 p156; the Prophet-love wording finds b12 p174. Source quotations and literal counts are not rewritten. Matching aliases are disclosed as `synonym_variant` where a local evidence span contains one.
- An explicit numbered heading read in paragraph mode returns its section through the next numbered heading or character cap. The b37 p156 heading now contains all four kinds. A capped section provides a continuation locator. Bounded reads keep their existing context policy.
- `reformulation_status` reports `degraded` only for a partial/skipped pipeline. Weak evidence is conveyed by `evidence_strength`. A short response declares `fewer_than_limit_reason` and the normalized count is no longer named literal.
- Lexeme search retains root-initial waw in وسواس and preserves written taa marbuta in الصدقة. It no longer counts the audited سواسية false positives.
- Relation labels reject the audited narrative companionship and formulaic prayer examples, require a remedy cue for anger remedies, and recognize an explicit death-preparation definition. They remain unverified candidates pending external grading.
- Mixed dialogue spans expose segment speakers and roles. An answer after a question mark without a fresh speaker marker remains an answer.
- The b37 metadata build derives a consistent source-author description from the supplied front matter and named compiler. Documentary review is still pending; reviewer and review date remain null.
- Monitoring history now records restarts and continues an observed window across process restarts when `MONITOR_SUMMARY_PATH` points to a mounted persistent volume. The default `/tmp` path is ephemeral and is explicitly labelled so.
- `changes_since_previous` now describes this release, including the heading and status changes.

## Verification

- Full suite: 301 passed, one third-party deprecation warning.
- Independent corpus audit: pass, 43 books and 6,935 pages; source corpus digest unchanged.
- 31 disclosed wordings: 0 errors; 29 question-form full, two lexical queries do not expose completion; local p95 399 ms. See `verification/2.10.12/public_replay.json`.
- Existing 30 disclosed reference cases: 27/30 references in top five, unchanged from the 2.10.10 reference replay; 0 errors, local p95 586 ms. Reference presence is not direct-answer grading. See `verification/2.10.12/reference_replay.json`.

## Outstanding acceptance

This package is not a verified 9/10 or 10/10 release. The auditor's 8.89/10 is a spot-audit score for the *deployed 2.10.11*, not a score for this un-deployed version. A 200-hit independent label review, the private 100-intent x three-wording Direct@5 gate, source coverage for genuinely absent answers, all-client schema checks, a persistent mounted monitoring path with seven days of samples, and live first-attempt/latency testing remain. No reviewer identity or provenance date has been invented.

Deployment: build the included Dockerfile from this package; set `MONITOR_SUMMARY_PATH` to a file on a persistent mounted volume (for example `/var/data/alburhaniya-monitor-history.json`) if the host supports one; verify `server_version=2.10.12`, `tool_contract_version=13.0`, refresh client schemas, then run the held-out grader and seven-day acceptance. Without a persistent volume the service reports monitoring as ephemeral and cannot pass that gate.

# Release 2.7.0 - assessment-driven improvements

## Requirement mapping

| Report item | Change / evidence | Remaining limit |
| --- | --- | --- |
| Preserve question intent | `question_intent.py`; source-local facets; function-word exclusion; livelihood positive and negative regression cases | Heuristic discovery; 40 proposed questions require independent grading |
| Complete paragraphs in clients | Fresh real MCP schema checks; single and batch paragraph offset/citation checks; stable bayt and qasida selectors | Existing clients must refresh tools/list; qasida selector intentionally returns the full structure |
| Search latency | Bounded immutable-text match caches; cached literal term lookup; repeated-sample before/after local benchmark | Production HTTP p50/p95 not measured |
| Non-zero omissions | Actual candidate snapshots; single, OR, AND, source/edition filters; equal-count substitutions; score/pagination negative controls | Literal census is based on the corpus/index, not independent OCR ground truth |
| Provenance and types | Boolean type fix at DB boundary; all-book triage inventory with hashes/date/source clues | No unsupported author/compiler upgrades |
| Token cost and catalogue | IDs-only projection, filtered full-metadata batch, actual tokenizer counts through local MCP | Model-specific context/billing varies; full metadata naturally costs more |
| Version/client discovery | 2.7.0 / contract 9.0; callable and capability digests; fresh five-tool discovery | Mid-deployment client recovery still needs the live client test |
| Optional semantic safety | Corpus hash and chunk-count guard; real metadata filtering tested on isolated DB copy | Original vectors are incompatible; regeneration/model quality untested |

## Compatibility notes

Contract 9.0 marks changed response semantics and selector validation. Existing
valid single-selector calls are preserved. Calls with multiple selectors or more
than 20 match IDs must be corrected; they now return an explicit error.
Search result fields are additive, except that reformulated score semantics are
now explicitly `local_intent_bm25_discovery`.

`retrieval_completeness` is always present on valid compact/ultra-compact searches.
It is not a claim of answer quality. Ordinary score filtering, diversification,
and pagination are deliberately outside the audit. AND per-query diagnostics are
restricted to combined AND-eligible pages, avoiding false omissions from pages
which satisfy only one alternative.

The audit can increase work for exact requests by inspecting candidates before
pagination. It is optional. It uses actual captured candidates for public calls;
the standalone DB helper's independent index check is labelled as a different method.

Caches contain pure functions of immutable source text and query/normalization
patterns, not search responses or page identities. New source bytes and changed
patterns use different keys. Bounded cache sizes prevent unlimited accumulation.
Rebuild indexes and restart workers when deploying corpus changes.

## Review honesty

The livelihood top five now include b41 sequences 130 and 131, which discuss
requests for provision and practical effort. Known mercy-only decoys b40/51 and
b39/324 are excluded. Other discovery results are not automatically verified
answers. No corpus-wide relevance percentage or external weighted score is inferred
from these targeted cases.

No source text, existing attribution, edition suppression rule, printed-page label,
stable bayt ID, or strict literal-normalization policy was deliberately changed.
The original semantic files are retained for traceability, not presented as usable.

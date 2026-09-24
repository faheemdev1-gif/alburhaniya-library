#!/usr/bin/env python3
"""Write the delivery report from current recorded checks; never invent a pass."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
v=ROOT/'verification/2.9.0'
checks=json.loads((v/'current_checks.json').read_text())
failed=[r for r in checks['checks'] if r['exit_code']]
if failed:raise SystemExit('Unresolved check failures: '+str(failed))
required={'fresh_build','sqlite_integrity','pytest','corpus_audit','negative_control','diwan_sweep','schema_export','provenance_inventory','public_replay','fresh_http','mixed_500','payload_measurement'}
if {r['check'] for r in checks['checks']}!=required:raise SystemExit('Incomplete verification pipeline')
pytest=(v/'pytest.log').read_text();match=re.search(r'(\d+) passed',pytest)
if not match:raise SystemExit('Missing pytest pass count')
load=json.loads((v/'local_500_calls.json').read_text());replay=json.loads((v/'public_replay.json').read_text())['summary'];diwan=json.loads((v/'diwan_sweep.json').read_text());payload=json.loads((v/'payload_measurements.json').read_text());prov=json.loads((ROOT/'data/provenance_review.json').read_text());open_records=[r for r in prov['records'] if r['review_status']=='documentary_review_required']
source_table='\n'.join('| '+r['book_id']+' | '+r['title'].replace('|','/')+' | '+r['existing_provenance_status']+' |' for r in open_records)
(ROOT/'docs/SOURCE_REVIEW_OPEN.md').write_text('# Open source verification records\n\n'+str(len(open_records))+' records require documentary review. Resolving them improves attribution confidence, not passage matching by itself. No authorship was upgraded without evidence.\n\n| Book | Title | Existing status |\n|---|---|---|\n'+source_table+'\n\nObtain original title pages, colophons, official catalogues or transmission evidence. Record reviewer, date and basis. Automated front/back-matter clues are in data/provenance_review.json; they are not proof.\n')
measure='\n'.join(f"| {r['fixture']} / {r['mode']} | {r['character_reduction_pct']}% | {r['before_tokens']} → {r['after_tokens']} |" for r in payload['results'])
report=f'''# Al Burhania 2.9.0 — fix report, 24 September 2026

## Delivery status

Updated source package; five MCP tools, contract 11.0. This is **not a live
Render deployment or certification that every assessment acceptance gate is
closed**. Original corpus and catalogue attribution are preserved. The code was
restored and verified against a freshly rebuilt index; historical logs outside
verification/2.9.0 do not describe this release.

## Current local verification

| Check | Result |
|---|---|
| Fresh source build / SQLite integrity | Both passed |
| Full automated suite | {match.group(1)} tests passed; dependency deprecation warning retained in log |
| Corpus audit / damaged-ID negative control | Audit passed; deliberate damage detected |
| Dīwān sweep | {diwan['passed']}/{diwan['qasidas']} poems; {diwan['bayts']} abyāt |
| Fresh HTTP MCP client | All five tools discovered/exercised; schema controls checked |
| Mixed local HTTP sample | {load['successful']}/{load['calls']} successful; two workers |
| Local mixed p95 | {load['p95_ms']} ms; repeated short-question p95 {load['question_p95_ms']} ms |
| Known public questions | {replay['known30_nonempty']}/30 nonempty; {replay['known30_reference_presence']}/30 original reference pages in top five |
| Newer public questions | {replay['public11_nonempty']}/11 nonempty; {replay['errors']} tool errors across both sets |
| Source inventory | {len(open_records)} records need documentary review, out of 43 |

Local HTTP times are from the fixed monitoring cycle, not a diverse question
latency study, production measurement or 24-hour observation. Nonempty output
and reference presence are **not direct-answer accuracy**. The older 2.8 local
replay had 27/30 original references; current alternatives need independent
grading, so public non-regression is not certified. No 9+ rating is assigned.

## Payload results on identical frozen citations and excerpts

| Fixture / mode | Character reduction | cl100k_base tokens, before → after |
|---|---|---|
{measure}

These isolate formatting using identical input rows; common transport/contract
envelopes are excluded. They are not an end-to-end ranking comparison with 2.8.
Two calls can perform search plus one bounded follow-up; human-verified-answer
cost has not been measured. Summary hides detailed authorship fields behind
get_book/detail=full while retaining confidence/status and source tier.

## Every PDF item: implementation and remaining acceptance work

“Implemented” below means local code and checks. Deployed and human-review
thresholds are separate; no external completion is implied.

| Item | Delivered change and expected improvement | Remaining acceptance |
|---|---|---|
| REL-1 | Origin MCP HTML guard returns a structured error; edge-rule instructions included. | Hosting owner must remove upstream browser challenges; origin code cannot intercept an earlier proxy response. |
| REL-2 | Per-client quota shared across local workers; JSON-RPC 429, Retry-After, retry_after_ms and remaining budget. | Configure client identity/authentication; multi-instance deployments need a shared quota service. |
| REL-3 | Two workers, bounded SDK threads, under-20-second deadline, SQLite interruption and truncated/structured budget responses. | Verify deployed capacity, memory and diverse question p95. |
| REL-4 | Question diagnostics use precomputed DF, not a per-word census; exact census cache includes scope, digest and file identity. | Local implementation tested. |
| REL-5 | 20-call monitor, >1% nonzero exit, rolling 24-hour sample summary and 15-minute scheduler example. | Activate scheduling, alert routing and history replication; collect real 24-hour samples. |
| REL-6 | Registry-derived schema endpoint/export, version/digest validation and fresh-client checks. | Refresh and test each external client/plugin. |
| RET-1 | Subject-phrase witnesses survive rewriting; passage/morphological/facet candidate union broadens discovery. | Independent accuracy and public non-regression remain ungraded. |
| RET-2 | True function words separate from DF-common nonanchors; domain nouns retained; keep_terms; general clitic/suffix/negation proposals. | Morphology remains a disclosed heuristic. |
| RET-3 | 500 source-derived topic proposals from contents/co-occurrences with offsets and unreviewed status; used for candidate expansion. | A reviewed 150-group, 25-area terminology taxonomy is not certified. |
| RET-4 | 700 recorded Q&A windows and 21,093 passage windows; question matches can display answers. | Within-page marker segmentation only; cross-page pairing and human precision review remain open. |
| RET-5 | Local topic/relation span scoring, tightness, reading cues and some blessing/narrative disambiguation. | General relevance, homograph and relation precision require review. |
| RET-6 | Near-identical excerpts collapse; alternate_locations retains citations and source tiers. | Test passes; corpus-wide paraphrase/duplicate recall unmeasured. |
| RET-7 | Optional vectors retained disabled. | Enable only if independent held-out evaluation demonstrates a gain. |
| RET-8 | External-owner runner validates 60 IDs, four phrasings and 20 topics. | Separate owner must provide, run and grade the private set. |
| CIT-1 | Answering-span excerpts; b07:166 prayer excerpt and follow-up tested. | Reviewed 95% excerpt-support threshold unmeasured. |
| CIT-2 | Repeated unreliable labels cite sequence only; repeats published in corpus contract. | Original scans still needed to restore actual printed pagination. |
| CIT-3 | Final scoring precedes sorting/pagination, including contents penalties. | Implemented and regression checked. |
| CIT-4 | Structural dialogue classification; hadith needs quoted/transmission cues, not the word أحاديث; heuristic/confidence disclosed. | 90% precision on 200 reviewed hits unmeasured; ambiguous source typography remains heuristic. |
| CIT-5 | Complete Dīwān numbering/stable-ID sweep. | All 95 pass locally. |
| PROV-1 | Full review inventory and review_basis disclosure; original attribution preserved. | {len(open_records)} documentary records remain open; target <=5 unmet. See docs/SOURCE_REVIEW_OPEN.md. |
| META-1 | Effective reformulated mode determines status; empty results cannot say not_needed. | Mawlid regression passes. |
| META-2 | Candidate support labels stay unverified; recorded question matches are not automatically direct answers. | Independent label calibration remains open; direct_answer is not fabricated. |
| META-3 | Exclusive phases, measured queue/auth time and serialization probe; sum and scope disclosed. | Network/proxy and final transport serialization are outside the measurement. |
| META-4 | Question/answer role and source-supported speaker; unnamed answer speakers stay unknown. | No inferred speaker identity. |
| DIAG-1 | Checked multiword retries before weak fallback, primary-aware ranking and low-tier-only warning. | Universal primary-source retry criterion on private questions remains unevaluated. |
| DIAG-2 | Dropped function words exposed, keep_terms supported. | Implemented and tested. |
| DIAG-3 | Missing literal-page and equal-count replacement negative controls retained. | Missing identities are detected, not merely unequal totals. |
| TOK-1 | Shared result_defaults with explicit per-hit overrides. | Contract 11 clients must expand defaults. |
| TOK-2 | Summary/full detail control; intent/normalization traces on request. | Rich metadata remains in full mode/get_book. |
| TOK-3 | Ultra-compact book ID/tier; detailed provenance via get_book. | Citation and excerpt text preserved. |
| TOK-4 | Character/UTF-8/token measurements on identical evidence. | End-to-end human-verified-answer cost remains unmeasured; see actual fixture savings above. |
| VER-1 | 2.9.0, contract 11, changes_since_previous, known_issues and actual callable schemas. | External deployment/client refresh still required. |

## Render startup and what remains

The screenshot establishes a health/port timeout, not its root cause. The
persistent launcher honors PORT, binds all interfaces, validates worker count,
checks index integrity/schema before spawning, and forwards shutdown signals.
A damaged/stale index now fails clearly instead of entering a respawn loop.
Deployment instructions cover root directory, command overrides and /health.
The actual failed Render deployment remains unverified until the corrected
source is deployed and observed through that hosting account.

To close the remaining PDF gates, the hosting owner must deploy/configure the
edge and clients, enable real monitoring, and run deployed acceptance checks.
Independent reviewers must grade retrieval, topic/Q&A proposals, excerpt and
evidence-type precision, and the private set. Documentary originals are needed
for attribution/pagination. The actual Docker/Python 3.11 image must also be
built and observed; local Python 3.12 checks do not certify that environment.

No original source text, catalogue author, external hosting rule, production
service, client configuration, email or alert destination was changed here.
Run/deploy instructions: README.md and docs/OPERATIONS_290.md.
Full current evidence: verification/2.9.0/current_checks.json and companion logs.
'''
(ROOT/'FIX_REPORT.md').write_text(report)
(v/'SUMMARY.md').write_text('# Current release verification\n\nFresh build and checks completed. See ../../FIX_REPORT.md and current_checks.json. This is local verification, not a deployed certification.\n')
print('Wrote current report with '+match.group(1)+' passed tests and '+str(len(open_records))+' open documentary records')

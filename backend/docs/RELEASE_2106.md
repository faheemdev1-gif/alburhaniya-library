# Al Burhaniya 2.10.6 source patch

## Live 2.10.5 findings

`/health` and all five connected tools report version 2.10.5, contract 12.0,
and the expected schema digest. The corrected scheduled monitor reported
19/20 successful samples, one `partial_completion`, and p95 about 5.3 seconds
at the time of review. Those are scheduled samples, not all traffic.

Four broad livelihood/distress prompts returned `full` from cache. Retesting
with a fresh cache key returned `partial` on all four. Each had an 80-passage
candidate union, skipped remaining scoring, and retained useful leading
results. Tool execution was about 4.7–6.5 seconds; connected-client wall time
was about 16–57 seconds for this four-call run. The client and server clocks
measure different work.

## Change

The livelihood (`provision`) and distress/relief intent groups now score at
most 40 source windows, with 20 rows from each FTS expression. Other subjects
retain 120 candidates, including citation-sensitive b07 p256. The scheduled
search probes request count auditing, which bypasses the result cache and
tests fresh scoring; partial responses remain monitor failures.

## Verification and limits

The final scoped candidate change passed 235 local tests. The public
30-question replay completed fully with listed reference presence in 27/30,
the same as 2.10.5. All four broad prompts completed locally with the same
reviewed leading passages. The four uncached count-audit probes completed
locally. The version and live regression subset passed 32/32 after the 2.10.6
label update.

Deploy 2.10.6 and retest cold broad prompts and the corrected monitor. The
local machine is substantially faster than the deployed environment, so this
patch cannot be considered live-verified yet. Client latency, sustained
monitoring, private held-out relevance grading, and documentary/source review
remain open before a 9+ score can be claimed.

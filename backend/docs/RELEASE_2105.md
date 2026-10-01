# Al Burhaniya 2.10.5 source patch

## Live 2.10.4 review

`/health` and all five connected tools report 2.10.4 with contract 12.0 and
the expected schema digest. The four earlier retrieval and attribution checks
still pass. Three scheduled search prompts returned `partial` while scoring
120 passage candidates: two livelihood prompts and one distress prompt. The
original sadness prompt was intermittent, returning both `partial` and `full`.
Server tool execution for the partial cases was about 4.6–4.7 seconds. Client
wall time was much longer and varies independently of server execution.

The new monitoring window reported 9 successes in 10 scheduled samples and
one `time_budget_exceeded`, with p95 about 18.1 seconds. Its earlier success
criterion also counted `partial` searches as successful, so that success rate
did not represent full search completion.

## Change

Livelihood (`provision`) and distress/relief questions use at most 80 passage
candidates (40 per FTS expression). Other subjects retain the 120-candidate
pool, including attribution-sensitive b07 p256. The scheduled monitor records
an incomplete search as `partial_completion`, with an explicit failure code.
No source text or five-tool schema changes were made.

## Verification and limits

The final scoped candidate change passed 235 local tests. The 30-question
public replay completed fully and retained a listed reference in 27/30,
unchanged from 2.10.4. Four formerly partial scheduled search prompts
completed locally with 80 candidates and retained their reviewed leading
pages. The version and live regression subset passed 32/32 after the 2.10.5
bump. Public
reference presence is not independent answer grading.

Deploy 2.10.5 and retest the four broad prompts without cache, all five tools,
`/health`, client latency and the corrected monitor. Sustained observation,
private held-out relevance grading, and documentary/source review remain
required before claiming a 9+ score. The client transport latency is not
resolved or certified by this server-side candidate bound.

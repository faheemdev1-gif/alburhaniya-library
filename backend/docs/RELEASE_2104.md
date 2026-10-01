# Al Burhaniya 2.10.4 source patch

## Live 2.10.3 findings

All five connected tools and `/health` report 2.10.3 with contract 12.0.
The four previously failing retrieval cases now behave as intended: b44 p43
for companionship, b07 p134 for sincerity and ostentation, an explicitly weak
one-sided inspiration comparison, and an empty weak result for the unrelated
mobile-phone ruling. Passage and page attribution guards are present.

The distress query `ما النصيحة لمن يشعر بالهم والحزن` returned useful results
but declared `partial` on three live attempts. Its 180-candidate passage
union spent roughly 4.2 seconds in window scoring on one measured attempt,
exhausting the 4.5-second stage budget. The client response wall time for the
eight reviewed searches ranged from about 11 to 40 seconds, considerably
longer than the server-reported tool execution times. These clocks include
different transport and connector work and must be measured separately.

The `/health` scheduled monitor reached 37 successes in 40 samples (92.5%),
with three `time_budget_exceeded` errors and a p95 near 18.2 seconds. This is
scheduled probe data, not all traffic. No 9+ or production acceptance claim
is made from these samples.

## Change and verification

The FTS passage candidate union is bounded to 120 windows and each expression
to 60 rows. The source ranking and evidence labels are unchanged. This
reduces scoring work for broad questions while retaining phrase candidates.

On the final source, 235 tests pass. In the local public 30-question replay,
all 30 completed, 27/30 retained a listed reference page (the same as
2.10.3), and the distress query completed. Reference presence is not answer
accuracy. The corpus, five-tool schema and contract 12.0 are unchanged.

After deployment, verify `server_version: 2.10.4`, repeat the distress query
without cache and the eight reviewed cases, then collect client wall timing
and scheduled monitor results. A clean observation window and independent
held-out/source review remain required before assigning a 9+ score. A source
patch cannot explain or certify the connector transport latency observed on
2.10.3.

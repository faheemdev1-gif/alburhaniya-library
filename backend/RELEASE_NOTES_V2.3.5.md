# Al Burhania connector v2.3.5

Tool contract: **5.6** (`alburhaniya-tools-v5`)  
Required public tools: exactly **5**

## Ultra-compact expansion fix

- Fixed `expand_top` being processed and then silently discarded by the
  `ultra_compact` serializer.
- Ultra-compact hits now retain requested bounded passage objects under `ep`.
  Compact hits continue to use `expanded_passage`.
- `expand_top=2` must produce exactly two expansions in both response modes.

## Scoped no-result cleanup

- A correctly spelled query with no result inside one qaṣīda no longer emits
  corpus-wide spelling suggestions, including the original query itself.
- Qaṣīda-scoped 0/0 counts remain authoritative and unchanged.

## Verification

- Regression result: **113 tests, 0 failures**; 1 optional semantic-vector
  test skipped because semantic vectors are intentionally not bundled.
- Gate totals: 107 hard, 3 retrieval-quality, and 2 efficiency checks passed;
  `deployment_blocked: false`.
- The production MCP gate now verifies both qaṣīda-scoped no-result behavior
  and `ultra_compact` expansion preservation.

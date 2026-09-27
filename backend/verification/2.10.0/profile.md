# Profile of the ten slowest measured question calls

Named exclusive wall durations from the final local replay; not CPU samples.

| Query | Seconds | Top three costs (milliseconds) |
|---|---:|---|
| L1 | 1.956934 | question_parsing: 1237.875; window_scoring: 627.448; excerpt_selection: 36.238 |
| L2 | 0.720125 | window_scoring: 690.575; excerpt_selection: 10.503; candidate_union: 8.585 |
| L2 | 0.702375 | window_scoring: 657.211; evidence_validation: 15.545; excerpt_selection: 10.104 |
| L1 | 0.684105 | window_scoring: 602.210; excerpt_selection: 37.834; deduplication: 15.431 |
| L1 | 0.670299 | window_scoring: 565.867; deduplication: 42.371; excerpt_selection: 35.834 |
| L2 | 0.65958 | window_scoring: 630.287; excerpt_selection: 10.357; candidate_union: 8.316 |
| L1 | 0.655751 | window_scoring: 580.896; excerpt_selection: 34.750; deduplication: 14.244 |
| L1 | 0.64408 | window_scoring: 568.796; excerpt_selection: 34.741; deduplication: 15.065 |
| L2 | 0.636187 | window_scoring: 608.139; excerpt_selection: 9.855; candidate_union: 8.329 |
| L2 | 0.634268 | window_scoring: 606.166; excerpt_selection: 9.840; candidate_union: 8.244 |

Window scoring is the principal repeated cost. First-process parsing includes compiled Arabic concept patterns. Warm responses use the corpus-bound cache. Excerpt and relation checks are bounded by candidate windows. Response building includes count-response assembly and metadata. Tiny cache-hit overhead can exceed a percentage target despite sub-millisecond absolute latency.

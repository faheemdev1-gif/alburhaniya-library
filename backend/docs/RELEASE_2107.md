# Al Burhaniya 2.10.7 retrieval patch

## Changes

- Extract the actual subjects from Arabic comparison, contrast and arrival
  questions. The generic words `مقام`, `المريد`, `أميز` and `بين` no longer
  qualify a page by themselves. Combining two practices keeps its practical
  intent plan, including the previously reviewed litanies and livelihood case.
- Expand candidate discovery for corpus-attested companions, dream vision,
  smoking spellings and reward language. The explicit deed-for-God versus
  praise-of-people wording discovers sincerity and showing-off passages.
  Original Arabic source and literal matching counts are unchanged.
- Require both query anchors in a source question before awarding Q&A credit.
  Yes/no dream questions require an answer cue before receiving a candidate
  relation label. Smoking mentions remain `topic_only` and `weak`; they are
  not a ruling. Reward ranking favors a direct local focus expression near
  the requested subject.
- Recognize `متى` and `ماذا` as question frames. The `متى يصل` wording now
  uses the bounded question path instead of a costly general hybrid fallback.

## Local verification

The public 30-question fixture is a reference-page presence check, not a
graded answer-quality score. The 2.10.6 baseline was 27/30; this patch
preserves the same 27/30 after restoring the practical combination case.
The three absent references are the existing distress paraphrases S2–S4.
The paired wording tests cover the newly reviewed comparison, sincerity,
companionship, dream and smoking cases. Run `python -m pytest -q` and
`python scripts/build_index.py` for a fresh deployment.
The 2.10.6 40-window bound for broad livelihood and distress searches and its
counted monitoring probes are retained.

## Acceptance still open

Deploy this version, refresh both client schemas, and independently grade
held-out queries and human-reviewed relevance labels before assigning a
retrieval score above 9. The report's sustained latency, restart, excerpt
and provenance gates also require separate production evidence. The five
tool contract remains 12.0.

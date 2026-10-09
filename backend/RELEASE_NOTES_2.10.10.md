# Al Burhaniya Connector 2.10.10 — retrieval repair

This release is based on the supplied 2.10.9 source archive. The authoritative book HTML and corpus mappings are preserved. `library.db` is generated during the Docker build and is excluded from this package.

## What changed

- Practical Arabic questions now give more weight to a nearby, explicit numbered set of conditions or steps when the requested subject is present. A passing mention of “conditions” alone does not receive that weight.
- The parser recognizes a general “what should someone do so that X is valid” question as a request for the conditions of X. It also recognizes the definite form of *maʿṣiya* and a common “return to God” wording when discovering repentance passages. These expansions select candidates; they never rewrite quotations or assert that a passage answers the question.
- The version and startup expectations are 2.10.10. The release package script uses the requested version in its ZIP folder name.
- A regression test covers four differently worded repentance questions and protects the weak-evidence status of a child-rearing question whose source passages do not establish a direct answer.

## Local checks

| Check | Result | Meaning |
| --- | ---: | --- |
| Complete test suite | 291 passed | Includes local startup, contract, citation, and retrieval regressions. |
| Independent corpus integrity audit | Pass | 43 books, 6,935 pages; no malformed or duplicate stable IDs; provenance audit passed. |
| Disclosed development questions | 27/30 reference pages in top five | Reference inclusion only. These cases were used during development and are not a blind score. |
| Formerly difficult topics | 11/11 nonempty | Nonempty search is not equivalent to a relevant answer. |
| New repentance paraphrases | 4/4 include the explicit conditions page in top five | The original how-to question and the “what must the penitent do” question rank the conditions page first. |
| Replay errors and local p95 | 0; 629 ms | Local Python calls on this machine, excluding HTTP and production load. |

The replay is in `verification/2.10.10/final_replay.json`; the integrity output is in `verification/2.10.10/corpus_audit.json`. Reproduce with `python scripts/verify_retrieval_2110.py` after `python scripts/build_index.py`.

## Remaining quality boundary

**A 9/10 answer-quality rating is not established.** A relevant top-five page is weaker evidence than a passage that directly answers the question. The supplied corpus has only passing child-rearing mentions for the tested wording. Searches about *fanāʾ* and *baqāʾ*, how to observe Laylat al-Qadr, and the view on Mawlid also need passage-level expert review; the top hits can mention a topic without answering the requested relation. The connector correctly keeps `answer_verified=false` rather than claiming verification.

To certify 9/10, use at least 40 independently owned Arabic questions across definition, comparison, practice, colloquial, and negation forms. Record whether a top-five excerpt directly answers each question, with a source citation, and measure live latency and errors. `scripts/evaluate_private_set.py` provides a response capture runner, but human passage grading remains necessary. Corpus gaps require adding and verifying authoritative source text, not tuning scores.

## Deployment check

Deploy this source through the backend repository's normal Docker build. The image build runs the full tests and corpus audit. After deployment, `/health` should report `server_version: 2.10.10`; then repeat the live connector search for the four repentance phrasings and the weak child-rearing case. The supplied archive does not include the backend repository or Render credentials, so this package has not been deployed and the live connector remains unverified for 2.10.10.

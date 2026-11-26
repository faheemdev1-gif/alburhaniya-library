# Al Burhaniya 2.10.20 release candidate

The local build recognizes additional Arabic question forms and a limited set of Urdu question patterns. It preserves Urdu spelling for multilingual embeddings, reports weak evidence on semantic-only result sets and requires verification for expanded lexeme hits. Dense search loads full text and metadata only for the selected vectors. Contract 15.1 remains compatible.

## Verification

Each retrieval check counts a hit when a reference page appears among the first five results. On the previously tested Arabic wordings, production 2.10.19 found 30 of 36 and the local candidate found 35. On 18 additional Arabic wordings of known topics chosen after implementation, local results moved from 9 to 10. On eight Urdu wordings they moved from 1 to 3. The separate semantic-only benchmark found its reference chunk on 21 of 30 questions. See verification/2.10.20/retrieval_checks.json for the question text and page IDs.

The candidate passed 377 tests on the project-pinned pytest version, 18 HTTP smoke checks, the corpus audit, and ten token-budget controls. Fresh Arabic and Urdu queries still miss known reference pages. Independent weighted grading and production deployment are pending.

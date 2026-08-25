# Release notes — v2.4.0 / tool contract 6.0

This is the research-integrity release.

## Fixed

- Whole-word matching is now the literal default; short Arabic words cannot
  match inside longer tokens.
- Safe normalization preserves hamza, ى/ي, and ة/ه for literal evidence and
  census arithmetic.
- Counts use an explicit, mode-independent `count_basis`.
- `auto` has a deterministic fallback chain and all zeroes return diagnostics.
- Explicit end-footnotes are excluded from authorial-body retrieval/counting.
- `get_page` defaults to 20,000 characters and always declares truncation.
- Qurʾān bracket direction is repaired in display output without rewriting the
  stored source.
- Schema capabilities are versioned and hashed for public parity checks.

## Added

- `min_tier` filtering.
- Provenance fields: compiler, authorship mode, attribution confidence, status.
- Full qaṣīda retrieval and stable-bayt lookup through `get_passage`.
- Optional, explicitly unverified Dīwān parallel candidates.
- Conservative content/evidence typing for Qurʾān, hadith, footnotes, headings.
- Independent matching/provenance audits and production schema smoke tests.

## Deliberately unresolved rather than guessed

- b42 compiler attribution is unverified; Safwat is not asserted.
- b01's tier remains provisional pending editorial provenance review.
- b23–b25 compilers remain unknown.
- Prosody metadata remains `not_curated` until independently verified.
- Semantic vectors are optional and are not shipped in this release.

## Compatibility

The connector still exposes exactly the same five tool names. New parameters
and response fields are additive. Deployments must rebuild `library.db` because
the safe-normalized FTS and provenance schema changed.

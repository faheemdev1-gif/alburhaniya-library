Al Burhaniya 2.10.2 overlay patch
=================================
Unzip this over your existing Al_Burhaniya_Connector_2.10.1 folder (same folder
name, overwrite when asked). Only changed and new files are included; raw corpus
files, embeddings and all other files are byte-identical to 2.10.1.

Then rebuild and verify as usual:
  python scripts/build_index.py
  python -m pytest -q            # expect 239 passed
  python scripts/independent_corpus_audit.py library.db

RELEASE_MANIFEST_2102.json lists SHA-256 for every file of the full 2.10.2 tree,
so you can confirm the overlay produced exactly the tested release.
Release notes: docs/RELEASE_2102.md

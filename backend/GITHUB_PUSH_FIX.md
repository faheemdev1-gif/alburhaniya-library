# Fix GitHub GH001 for `backend/library.db`

GitHub rejected the push because `backend/library.db` is 211.59 MB. Release
2.3.2 does not track that generated file: Docker builds it from the source
books before running the regression gate.

The rejected commits never reached GitHub, so rewrite only the local unpushed
history while preserving every working-tree change:

```bash
cd /path/to/alburhaniya-library
git fetch origin
git reset --soft origin/main
git rm --cached --ignore-unmatch backend/library.db
git add .
git status
git commit -m "Deploy Al Burhania connector v2.3.2"
git push origin main
```

Before committing, `git status` must not list `backend/library.db` under
"Changes to be committed". The file may remain on your computer as an ignored
local build artifact.

For local development, rebuild it from the backend directory:

```bash
cd backend
python scripts/build_index.py
python scripts/run_regression_suite.py
```

Do not use Git LFS for this database. It is reproducible, changes whenever the
corpus/index format changes, and belongs in the Docker build rather than source
control.

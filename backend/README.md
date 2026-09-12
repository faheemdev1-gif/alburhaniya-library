# Burhaniya library backend

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the 2.6.0 fixes, evidence, remaining
editorial work and deployment instructions.

```bash
python -m pip install -r requirements.txt
python scripts/build_index.py
python scripts/run_regression_suite.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The MCP endpoint is `/mcp/`. The database is generated; source text and optional
semantic artifacts are included. Semantic search remains disabled by default.

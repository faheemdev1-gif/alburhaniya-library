# SQLite FTS5 plus citation-safe research indexes. Semantic vectors remain optional.
FROM python:3.11-slim

WORKDIR /app

# Optional legacy PDF/DOCX ingestion dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt requirements-dev.txt ./
ENV PIP_DEFAULT_TIMEOUT=120
RUN python -m pip install \
    --no-cache-dir \
    --retries 10 \
    --timeout 120 \
    -r requirements-dev.txt
COPY . .

# library.db is a generated build artifact (over 100 MiB with research
# indexes), so it is never committed to Git. Build it reproducibly from the
# authoritative source texts inside the image instead.
RUN test -s data/raw_htm/book_14.htm \
    && python scripts/build_index.py

# Deployment gate: hard citation/structure failures and retrieval-quality
# regressions fail the image build; efficiency issues are reported separately.
RUN python -m pytest -q \
    && python scripts/independent_corpus_audit.py library.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# SQLite FTS5 plus citation-safe research indexes. Semantic vectors remain optional.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Optional legacy PDF/DOCX ingestion dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-lock.txt ./
ENV PIP_DEFAULT_TIMEOUT=120
RUN python -m pip install \
    --no-cache-dir \
    --retries 10 \
    --timeout 120 \
    -r requirements-lock.txt
COPY . .

# library.db is a generated build artifact (over 100 MiB with research
# indexes), so it is never committed to Git. Build it reproducibly from the
# authoritative source texts inside the image instead.
RUN test -s data/raw_htm/book_14.htm \
    && python scripts/build_index.py

# Deployment gate: hard citation/structure failures and retrieval-quality
# regressions and measured token-budget growth fail the image build.
RUN python -m pytest -q \
    && python scripts/independent_corpus_audit.py library.db \
    && python scripts/measure_workflow_2115.py \
    && python scripts/check_token_budgets.py

EXPOSE 8000

CMD ["python", "scripts/start_server.py"]

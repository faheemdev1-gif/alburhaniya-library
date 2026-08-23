# SQLite FTS5 plus a prebuilt multilingual E5 semantic index.
FROM python:3.11-slim

WORKDIR /app

# Optional legacy PDF/DOCX ingestion dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ENV PIP_DEFAULT_TIMEOUT=120
RUN python -m pip install \
    --no-cache-dir \
    --retries 10 \
    --timeout 120 \
    -r requirements.txt
COPY . .

# The lexical corpus is authoritative. Semantic artifacts are optional and
# activate only when explicitly supplied and ENABLE_LOCAL_SEMANTIC_SEARCH=true.
RUN test -s library.db \
    && test -s data/raw_htm/book_14.htm

# Deployment gate: hard citation/structure failures and retrieval-quality
# regressions fail the image build; efficiency issues are reported separately.
RUN python scripts/run_regression_suite.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

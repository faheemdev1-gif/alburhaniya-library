# SQLite FTS5 plus a local multilingual E5 semantic index. The model and
# corpus vectors are built into the image; no vector database or persistent
# disk is required.
FROM python:3.11-slim

WORKDIR /app

# libmagic/poppler kept for the optional legacy PDF/DOCX ingestion pipeline
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build library.db (SQLite FTS5) from data/raw_htm — baked into this image,
# so no persistent disk is needed at runtime. Any redeploy rebuilds it fresh.
RUN python scripts/build_index.py
RUN python scripts/build_semantic_index.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

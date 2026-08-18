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
# Keep the model inside the Docker image.
# This downloads the model but does not rebuild corpus embeddings.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"

COPY . .

# Fail immediately if prebuilt artifacts are missing from Git/Docker context
RUN test -s library.db \
    && test -s semantic_embeddings.npy \
    && test -s semantic_manifest.json

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
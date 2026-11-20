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

# Build with --build-arg WITH_E5=1 to publish a self-contained semantic image.
ARG WITH_E5=0
RUN if [ "$WITH_E5" = 1 ]; then \
      python -m pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && \
      python -m pip install --no-cache-dir 'sentence-transformers==5.1.2' 'transformers==4.51.3' && \
      python scripts/build_semantic_index.py --verify-packaged && \
      python -c "import json; from huggingface_hub import snapshot_download; m=json.load(open('semantic_manifest.json')); snapshot_download(m['model'], revision=m['model_revision'], allow_patterns=['*.json','model.safetensors','sentencepiece.bpe.model'], ignore_patterns=['onnx/*','openvino/*'])" && \
      ENABLE_LOCAL_SEMANTIC_SEARCH=true HF_HUB_OFFLINE=1 python -c "from app.services.semantic_search import semantic_search; assert semantic_search('آداب المريد', book_ids=['b14'], limit=1)"; \
    else test "$WITH_E5" = 0; fi
ENV ENABLE_LOCAL_SEMANTIC_SEARCH=${WITH_E5}

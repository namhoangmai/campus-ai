# Campus-AI backend — Tier 1 deployment image (single instance, not horizontally scaled; see
# ARCHITECTURE.md §9's local/cloud table). Build from the `backend/` directory as context:
#
#   docker build -t campus-ai-backend -f Dockerfile .        (run from backend/)
#
# REQUIRED VOLUME: TENANT_DATA_DIR (default /app/data/tenants inside this image — see
# app/config.py's REPO_ROOT/tenant_data_dir) holds every tenant's raw uploaded documents AND its
# per-tenant Chroma vector store (backend/app/retrieval/, backend/app/ingestion/ — see
# AGENTS.md/CLAUDE.md's "do-not-touch" list, this content plane is never regenerated from
# anything else). It MUST be mounted as a persistent volume (or bind-mounted to durable storage)
# in any deployment of this image. Redeploying a container without that volume attached silently
# deletes every tenant's documents and search index — there is no backup copy anywhere else.
# Example: `docker run -v campus_ai_tenant_data:/app/data/tenants ...`.
#
# Also required (control plane): a reachable Postgres via DATABASE_URL — this image does not
# bundle a database (see docker-compose.yml for local dev only).
#
# NOTE: backend/requirements.txt pins no versions as of this writing, so this image's dependency
# set is not fully reproducible build-to-build. That's a pre-existing gap in requirements.txt,
# not something this Dockerfile works around — flagged, not fixed here (out of this job's scope).

# ---- Builder: install deps into a venv, bake the embedding model into the image ----
FROM python:3.12-slim AS builder

# hnswlib (a chromadb dependency) needs a compiler if no prebuilt wheel matches this platform.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app/backend
COPY requirements.txt .
# --extra-index-url prefers PyTorch's CPU-only wheels over PyPI's default CUDA build for
# `torch` (a sentence-transformers dependency) -- much smaller, and this image never uses a GPU.
# Pure Docker-layer optimization; does not change what requirements.txt declares.
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Bake BAAI/bge-m3 (app/config.py's default EMBEDDING_MODEL, loaded by
# app/retrieval/vector_store.py via SentenceTransformerEmbeddingFunction) into the image so a
# cold production request never blocks on a multi-GB first-use download
# (ARCHITECTURE-ESSENTIALS.md). HF_HOME is carried into the runtime stage below unchanged so the
# cache is found at the same path, not re-downloaded. If EMBEDDING_MODEL is overridden away from
# the default at deploy time, that different model still downloads on first use -- mount
# HF_HOME as a persistent volume too in that case, or add another RUN line here for it.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

COPY . .

# ---- Runtime: slim image, no compiler, non-root ----
FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --home /app app

ENV PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf-cache \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf-cache /opt/hf-cache
COPY --from=builder /app/backend /app/backend

RUN chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

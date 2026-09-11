# Campus-AI backend API — Tier 1 by default (single instance, not horizontally scaled), Tier 2
# cloud infra opt-in via env vars (see ARCHITECTURE.md §9's local/cloud table). Build from the
# `backend/` directory as context:
#
#   docker build -t campus-ai-backend -f Dockerfile .        (run from backend/)
#
# REQUIRED VOLUME: TENANT_DATA_DIR (default /app/data/tenants inside this image — see
# app/config.py's REPO_ROOT/tenant_data_dir) always holds the per-tenant Chroma vector store
# (backend/app/retrieval/ — see AGENTS.md/CLAUDE.md's "do-not-touch" list, this content plane is
# never regenerated from anything else). It ALSO holds raw uploaded documents when S3_BUCKET is
# unset (LocalDiskStorage, app/storage.py). It MUST be mounted as a persistent volume (or
# bind-mounted to durable storage) in any deployment of this image regardless of S3_BUCKET.
# Redeploying a container without that volume attached silently deletes every tenant's search
# index (and, without S3_BUCKET, its raw documents too) — there is no backup copy anywhere else.
# Example: `docker run -v campus_ai_tenant_data:/app/data/tenants ...`.
#
# TIER 2 (ARCHITECTURE.md §9/§12, opt-in via env vars, unset = Tier 1 behavior unchanged):
#   S3_BUCKET (+ S3_ENDPOINT_URL/S3_ACCESS_KEY_ID/S3_SECRET_ACCESS_KEY/S3_REGION) moves raw
#     document storage off this container's volume onto S3-compatible object storage (Cloudflare
#     R2 by default) -- app/storage.py:S3Storage. Existing raw files already on the volume are
#     NOT migrated by turning this on; see the job report for that as a separate, explicit step.
#   REDIS_URL switches the rate limiter to Redis (shared across instances) AND switches
#     POST /api/admin/tenants/{slug}/documents to enqueue a background job instead of ingesting
#     inline -- that job is only actually processed if a worker service is also running from
#     Dockerfile.worker, pointed at the SAME REDIS_URL/DATABASE_URL/TENANT_DATA_DIR/S3_* values
#     as this API service. Setting REDIS_URL without deploying that worker leaves every upload
#     stuck in "processing" forever.
#
# Also required (control plane): a reachable Postgres via DATABASE_URL — this image does not
# bundle a database (see docker-compose.yml for local dev only).
#
# NOTE: most of backend/requirements.txt pins no versions as of this writing (the Tier 2
# additions -- boto3/redis/rq -- are the exception), so this image's dependency set is not fully
# reproducible build-to-build for the rest of the file. That's a pre-existing gap, not something
# this Dockerfile works around — flagged, not fixed here (out of this job's scope).

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

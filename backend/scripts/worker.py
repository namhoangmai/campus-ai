"""Background-job worker for document ingestion (ARCHITECTURE.md §9/§12's Tier 2 swap).

Pulls jobs off the same Redis queue routers/admin.py:upload_document enqueues to whenever
REDIS_URL is set, and runs them via app.routers.admin:process_ingestion_job, which in turn calls
app.ingestion.pipeline.ingest_document() -- that function needed zero changes to move from
"called synchronously inside a request" to "called here," per its own module docstring.

Deploy as its own process/Railway service, off the same image as the API
(backend/Dockerfile.worker) and the same REDIS_URL / DATABASE_URL / TENANT_DATA_DIR / S3_*
settings the API uses -- it needs to reach the same Postgres, Redis, and content-plane storage.

Usage (from backend/, with REDIS_URL pointed at the same Redis the API uses). Run with `-m`,
not as a bare script path -- a bare `python scripts/worker.py` puts scripts/ (not backend/) on
sys.path, and `app` won't be importable:

    python -m scripts.worker
"""

from rq import Worker

from app.config import INGESTION_QUEUE_NAME, get_settings
from app.routers.admin import process_ingestion_job  # noqa: F401 -- imported so this process can
# resolve the job's module path (app.routers.admin.process_ingestion_job) when RQ hands it back.
from app.security import get_redis_connection


def main() -> None:
    if not get_settings().redis_url:
        raise RuntimeError("REDIS_URL is not set -- this worker has no queue to listen on.")
    Worker([INGESTION_QUEUE_NAME], connection=get_redis_connection()).work()


if __name__ == "__main__":
    main()

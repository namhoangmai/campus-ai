"""Unauthenticated liveness check. No dependency on the database or vector stores on purpose —
this endpoint answers "is the process up," not "is the system healthy," so it can't itself
become a source of false-negative uptime alerts if Postgres or a tenant store is briefly down.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

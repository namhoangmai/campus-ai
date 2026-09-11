"""FastAPI application factory and router mounting.

Replaces v1's `backend/main.py`, which bootstrapped `sys.path` and `os.chdir` at import time so
that `src/scrape`/`src/rag` modules could use bare, non-package imports (see
ARCHITECTURE-ESSENTIALS.md's v1 "gotchas" list — nothing under v1's `src/` imported cleanly
outside that bootstrap). `backend/app/` is a normal, installable Python package instead: every
import here is a real package-qualified import (`from app.routers import ...`), which works
identically whether the app is started via `uvicorn app.main:app`, imported in a test file, or
loaded in a REPL — no bootstrap required.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, chat, health

app = FastAPI(title="Campus-AI API")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(admin.router)
app.include_router(chat.router)

"""Create the control-plane tables in Postgres.

A single `Base.metadata.create_all()`, not an Alembic migration chain — deliberate for this
phase, because the schema (app/models.py) is still settling and there is no production data yet
that a bare `create_all` diff would fail to update correctly. ARCHITECTURE.md §12 names the
point at which Alembic gets adopted: the moment there's real tenant data an in-place schema
change would need to preserve. Run this once before starting the API for the first time, or
after a schema change, against a fresh database:

    python init_db.py
"""

from app.db import Base, engine
from app import models  # noqa: F401 - import registers the models with Base.metadata


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Control-plane tables created (or already present).")


if __name__ == "__main__":
    main()

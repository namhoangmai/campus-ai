"""One-off migration: import v1's scraped TU/e Markdown pages into the v2 multi-tenant system.

Creates (or reuses) the "tue" tenant and runs every file in v1's `data/TUE/raw/*.md` through the
*current* markdown ingestion pipeline — a real re-ingestion, not a data copy. This is deliberate
(ARCHITECTURE.md §11): v1's `build_index.py` had two bugs that meant only 1 of 11 scraped
documents actually made it into the index (see ARCHITECTURE-ESSENTIALS.md's v1 "burn you" list,
item 6). Re-ingesting through the fixed v2 pipeline resolves that as a side effect instead of
needing a separate bugfix-then-migrate step.

Run once, from backend/, against a running Postgres (see ../docker-compose.yml) with tables
already created (`python init_db.py`):

    python scripts/migrate_v1_tue_data.py --legacy-raw-dir ../data/TUE/raw
"""

import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import app.*` works when run directly

from app.db import SessionLocal
from app.ingestion.pipeline import ingest_document
from app.models import Tenant
from app.security import generate_widget_key

app = typer.Typer(add_completion=False)


@app.command()
def main(
    legacy_raw_dir: Path = typer.Option(..., exists=True, file_okay=False),
    tenant_slug: str = "tue",
    tenant_name: str = "Eindhoven University of Technology",
) -> None:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            tenant = Tenant(slug=tenant_slug, name=tenant_name, widget_key=generate_widget_key(tenant_slug))
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            typer.secho(f"Created tenant '{tenant_slug}'. widget_key: {tenant.widget_key}", fg=typer.colors.GREEN)
        else:
            typer.echo(f"Tenant '{tenant_slug}' already exists, reusing it.")

        md_files = sorted(legacy_raw_dir.glob("*.md"))
        typer.echo(f"Found {len(md_files)} legacy Markdown file(s) in {legacy_raw_dir}")

        for path in md_files:
            content = path.read_bytes()
            doc = ingest_document(db, tenant, path.name, content)
            color = typer.colors.GREEN if doc.status == "indexed" else typer.colors.RED
            typer.secho(f"  {doc.status:<10} {path.name} (chunks={doc.chunk_count})", fg=color)
            if doc.status == "failed":
                typer.echo(f"    error: {doc.error_message}")
    finally:
        db.close()


if __name__ == "__main__":
    app()

"""Operator CLI for tenant provisioning and document management.

A thin HTTP client over the `/api/admin/*` endpoints (app/routers/admin.py) — not a separate
code path that talks to the database or vector stores directly. That's deliberate
(ARCHITECTURE.md §10): when self-serve onboarding is built later, it calls the same endpoints
from a web dashboard instead of this CLI, so none of the ingestion or tenancy logic changes,
only who's allowed to call it and through what interface.

Usage (run from backend/, with the API already running):

    export CAMPUS_AI_ADMIN_KEY=...       # must match ADMIN_API_KEY in .env
    python scripts/admin_cli.py create-tenant --slug tue --name "Eindhoven University of Technology"
    python scripts/admin_cli.py upload --tenant tue --file ./syllabus.pdf
    python scripts/admin_cli.py upload --tenant tue --dir ./tue-documents/
    python scripts/admin_cli.py list-documents --tenant tue
    python scripts/admin_cli.py delete --tenant tue --document-id <id>
    python scripts/admin_cli.py list-tenants
"""

import os
from pathlib import Path

import httpx
import typer

app = typer.Typer(add_completion=False)

API_BASE = os.environ.get("CAMPUS_AI_API_URL", "http://localhost:8000")


def _headers() -> dict[str, str]:
    key = os.environ.get("CAMPUS_AI_ADMIN_KEY")
    if not key:
        typer.secho("CAMPUS_AI_ADMIN_KEY is not set in the environment.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    return {"X-Admin-Key": key}


@app.command("create-tenant")
def create_tenant(slug: str = typer.Option(...), name: str = typer.Option(...)) -> None:
    resp = httpx.post(f"{API_BASE}/api/admin/tenants", json={"slug": slug, "name": name}, headers=_headers())
    if resp.status_code >= 400:
        typer.secho(f"Failed ({resp.status_code}): {resp.text}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    data = resp.json()
    typer.secho(f"Created tenant '{data['slug']}'.", fg=typer.colors.GREEN)
    typer.echo(f"  widget_key: {data['widget_key']}")
    typer.echo("  Give this key + the widget-loader snippet to the university's webmaster.")
    typer.echo("  It will not be shown again by this API — store it now.")


@app.command("list-tenants")
def list_tenants() -> None:
    resp = httpx.get(f"{API_BASE}/api/admin/tenants", headers=_headers())
    resp.raise_for_status()
    for t in resp.json():
        typer.echo(f"{t['slug']:<20} {t['name']:<50} {t['status']}")


@app.command("upload")
def upload(
    tenant: str = typer.Option(...),
    file: Path = typer.Option(None, exists=True, dir_okay=False),
    dir: Path = typer.Option(None, exists=True, file_okay=False),
) -> None:
    if not file and not dir:
        typer.secho("Pass either --file or --dir.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    files = [file] if file else sorted(p for p in dir.iterdir() if p.suffix.lower() in (".md", ".markdown", ".pdf"))
    for path in files:
        with path.open("rb") as fh:
            resp = httpx.post(
                f"{API_BASE}/api/admin/tenants/{tenant}/documents",
                files={"file": (path.name, fh)},
                headers=_headers(),
                timeout=120.0,
            )
        if resp.status_code >= 400:
            typer.secho(f"  FAILED {path.name}: {resp.status_code} {resp.text}", fg=typer.colors.RED)
            continue
        doc = resp.json()
        color = typer.colors.GREEN if doc["status"] == "indexed" else typer.colors.YELLOW
        typer.secho(f"  {doc['status']:<10} {path.name} ({doc.get('chunk_count')} chunks)", fg=color)


@app.command("list-documents")
def list_documents(tenant: str = typer.Option(...)) -> None:
    resp = httpx.get(f"{API_BASE}/api/admin/tenants/{tenant}/documents", headers=_headers())
    resp.raise_for_status()
    for d in resp.json():
        typer.echo(f"{d['status']:<10} {d['filename']:<40} chunks={d.get('chunk_count')} pages={d.get('page_count')}")


@app.command("delete")
def delete_document(tenant: str = typer.Option(...), document_id: str = typer.Option(...)) -> None:
    resp = httpx.delete(f"{API_BASE}/api/admin/tenants/{tenant}/documents/{document_id}", headers=_headers())
    if resp.status_code >= 400:
        typer.secho(f"Failed ({resp.status_code}): {resp.text}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"Deleted document '{document_id}' from tenant '{tenant}'.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()

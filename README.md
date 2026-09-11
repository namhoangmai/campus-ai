# Campus-AI

A multi-tenant document Q&A chatbot any university can embed on its own website as a pop-up
widget. Each university (tenant) uploads its own documents (Markdown, PDF); the widget answers
student questions from that university's documents only, with citations. See `PRD.md` for what
this is and why, and `ARCHITECTURE.md` for the full technical design and the reasoning behind
every decision. `FILES.md` describes every file in this repo. `MIGRATION.md` covers what changed
from the original single-tenant, TU/e-only, web-scraping version of this project.

## Quickstart (local development)

**1. Control-plane database**

```
docker compose up -d
```

**2. Backend**

```
cd backend
python -m venv .venv && # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in ADMIN_API_KEY and OPENROUTER_API_KEY
python init_db.py
python -m uvicorn app.main:app --reload --port 8000
```

Confirm it's up: `curl http://localhost:8000/api/health` → `{"status": "ok"}`.

**3. Frontend**

```
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

**4. Onboard your first tenant**

```
cd backend
$env:CAMPUS_AI_ADMIN_KEY=<the ADMIN_API_KEY you set in .env>
python scripts/admin_cli.py create-tenant --slug tue --name "Eindhoven University of Technology"
python scripts/admin_cli.py upload --tenant tue --dir ./your-documents/
```

The `create-tenant` command prints a `widget_key` — that's what goes into the embed snippet:

```html
<script src="http://localhost:3000/widget-loader.js" data-widget-key="pk_tue_..."></script>
```

Open any static HTML page with that snippet in a browser (with the backend and frontend both
running) and you'll see the chat bubble.

**Migrating existing v1 TU/e data?** See `MIGRATION.md`.

## Running the tests

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m pytest tests/ -v
```

No Postgres server needed for tests — `backend/tests/conftest.py` uses a temporary SQLite file
for the control plane and a deterministic fake embedding function instead of downloading the real
model, so the suite (including `test_tenancy_isolation.py`, the release-gate test described in
`ARCHITECTURE.md` §13) runs anywhere with no external dependencies or network access.

## Repo layout

See `FILES.md` for a one-paragraph description of every file. High level:

```
backend/app/          FastAPI application (config, db, models, ingestion, retrieval, generation, routers)
backend/scripts/       Admin CLI + the v1-data migration script
backend/tests/         pytest suite, including the tenant-isolation release gate
frontend/app/widget/   The chat UI loaded inside a tenant's embedded iframe
frontend/public/       widget-loader.js -- what a university actually pastes into its site
data/tenants/           Per-tenant content plane (raw documents + vector store), gitignored
ARCHITECTURE.md         Full technical design + rationale (read this first for "why")
PRD.md                  Product requirements
MIGRATION.md            What changed from v1, and how to bring v1 data forward
FILES.md                One paragraph per file in this repo
```

"""Admin-only routes: tenant provisioning and document management.

Every route here depends on `require_admin` (app/deps.py) — the operator's admin key — and
every route that touches a specific tenant's data takes that tenant's `slug` from the URL path,
resolved via `get_tenant_by_slug`. There is no route in this file that infers "which tenant" from
anything other than an explicit, admin-supplied slug: unlike the widget-key chat path, admin
routes are allowed to name any tenant, because the admin key itself is the trust boundary here
(ARCHITECTURE.md §7).
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_tenant_by_slug, require_admin
from app.ingestion.pipeline import UnsupportedDocumentType, ingest_document
from app.models import Document, Tenant
from app.schemas import DocumentResponse, TenantCreateRequest, TenantCreatedResponse, TenantResponse
from app.security import generate_widget_key

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@router.post("/tenants", response_model=TenantCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(req: TenantCreateRequest, db: Session = Depends(get_db)) -> TenantCreatedResponse:
    if db.query(Tenant).filter(Tenant.slug == req.slug).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tenant '{req.slug}' already exists.")

    tenant = Tenant(slug=req.slug, name=req.name, widget_key=generate_widget_key(req.slug))
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantCreatedResponse(
        id=tenant.id, slug=tenant.slug, name=tenant.name, status=tenant.status,
        created_at=tenant.created_at, widget_key=tenant.widget_key,
    )


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)) -> list[Tenant]:
    return db.query(Tenant).order_by(Tenant.created_at).all()


@router.get("/tenants/{slug}", response_model=TenantResponse)
def get_tenant(tenant: Tenant = Depends(get_tenant_by_slug)) -> Tenant:
    return tenant


@router.post("/tenants/{slug}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant_by_slug),
    db: Session = Depends(get_db),
) -> Document:
    content = await file.read()
    try:
        return ingest_document(db, tenant, file.filename or "untitled", content)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/tenants/{slug}/documents", response_model=list[DocumentResponse])
def list_documents(tenant: Tenant = Depends(get_tenant_by_slug), db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).filter(Document.tenant_id == tenant.id).order_by(Document.uploaded_at).all()

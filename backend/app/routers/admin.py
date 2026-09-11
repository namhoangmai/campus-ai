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
from app.retrieval.vector_store import get_store
from app.schemas import DocumentResponse, TenantCreateRequest, TenantCreatedResponse, TenantResponse
from app.security import generate_widget_key
from app.storage import get_storage

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


@router.delete("/tenants/{slug}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    tenant: Tenant = Depends(get_tenant_by_slug),
    db: Session = Depends(get_db),
) -> None:
    """Removes one document's chunks (vector store), raw file (storage), and Document row.
    Scoped to `tenant` from the URL path, not just `document_id` alone, so an admin can never
    delete a document by guessing an id that belongs to a different tenant (404, not 403 -- same
    "don't even confirm it exists" posture as get_tenant_by_slug/resolve_tenant_from_widget_key).
    `source_id` (vector store) is the document's filename, not a separately stored field -- see
    ingestion/pipeline.py:ingest_document, which derives it from filename alone. The raw-storage
    ref is reconstructed via Storage.raw_ref (app/storage.py) rather than read off a stored
    column, because Document doesn't persist save_raw()'s return value -- see that method's
    docstring for why, and the more robust alternative this flags instead of making silently."""
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.tenant_id == tenant.id)
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No document '{document_id}' for tenant '{tenant.slug}'.",
        )

    get_store(tenant.slug).delete_by_source(document.filename)

    storage = get_storage()
    storage.delete_raw(tenant.slug, storage.raw_ref(tenant.slug, document.checksum, document.filename))

    db.delete(document)
    db.commit()

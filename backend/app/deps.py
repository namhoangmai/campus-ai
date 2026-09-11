"""FastAPI dependencies: database session, admin-key enforcement, widget-key → Tenant resolution.

These are the functions routers actually call to find out "who is asking, and what are they
allowed to touch." Keeping tenant resolution here (rather than inline in each router) means
there is exactly one implementation of "turn a widget key into a Tenant" to audit — see
`resolve_tenant_from_widget_key`, which is the function ARCHITECTURE.md §7 refers to as "the
only function in the codebase allowed to do that lookup."
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tenant
from app.security import is_admin_key_valid


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Route dependency for every /api/admin/* endpoint. Raises before any tenant-scoped
    logic runs if the caller doesn't hold the operator's admin key."""
    if not is_admin_key_valid(x_admin_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing admin key.")


def get_tenant_by_slug(slug: str, db: Session = Depends(get_db)) -> Tenant:
    """Admin-path tenant lookup, by slug from the URL path — used only behind `require_admin`.
    Not to be confused with the widget-key resolver below: this trusts the caller (already
    authenticated as admin) to name any tenant; the widget-key resolver below trusts nothing
    but the credential itself."""
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No tenant '{slug}'.")
    return tenant


def resolve_tenant_from_widget_key(
    x_widget_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    """The only place a widget key is turned into a Tenant. `/api/chat` depends on this instead
    of accepting a `tenant_slug` field in its request body, specifically so a client can never
    ask to chat "as" a tenant other than the one its key belongs to (ARCHITECTURE.md §7)."""
    if not x_widget_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing widget key.")
    tenant = (
        db.query(Tenant)
        .filter(Tenant.widget_key == x_widget_key, Tenant.status == "active")
        .first()
    )
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive widget key.")
    return tenant

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..audit_log import log_event, snapshot_row
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, get_current_user, has_global_access,
)
from ..models import Lease, Tenant, User
from ..schemas import TenantCreate, TenantOut, TenantUpdate

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

_TENANT_FIELDS = [
    "id", "first_name", "last_name", "email", "phone", "guarantor_name",
]


def _tenant_label(t: Tenant) -> str:
    return f"{t.last_name} {t.first_name}".strip()


def _tenant_linked_property_ids(db: Session, tenant_id: int) -> set[int]:
    rows = db.query(Lease.property_id).filter(Lease.tenant_id == tenant_id).distinct().all()
    return {row[0] for row in rows}


def _tenant_visible_to(db: Session, user: User, tenant_id: int) -> bool:
    if has_global_access(user):
        return True
    accessible = accessible_property_ids(db, user) or set()
    linked = _tenant_linked_property_ids(db, tenant_id)
    # Visible if at least one linked property is accessible OR the tenant has
    # no leases yet (in which case we treat it as universally visible — only
    # admins can have brand-new orphan tenants in practice; non-admin users
    # who just created a tenant will follow up by creating a lease on a
    # property they already control).
    if not linked:
        return True
    return bool(linked & accessible)


@router.get("", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if has_global_access(user):
        return db.query(Tenant).order_by(Tenant.last_name, Tenant.first_name).all()
    accessible = accessible_property_ids(db, user) or set()
    if not accessible:
        return []
    q = (
        db.query(Tenant)
        .join(Lease, Lease.tenant_id == Tenant.id)
        .filter(Lease.property_id.in_(accessible))
        .distinct()
        .order_by(Tenant.last_name, Tenant.first_name)
    )
    return q.all()


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tenant = Tenant(**body.model_dump())
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    log_event(
        db, user, action="create", entity_type="tenant",
        entity_id=str(tenant.id), entity_label=_tenant_label(tenant),
        after=snapshot_row(tenant, _TENANT_FIELDS),
    )
    return tenant


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant or not _tenant_visible_to(db, user, tenant_id):
        raise HTTPException(404, "Locataire introuvable")
    return tenant


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, body: TenantUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant or not _tenant_visible_to(db, user, tenant_id):
        raise HTTPException(404, "Locataire introuvable")
    before = snapshot_row(tenant, _TENANT_FIELDS)
    for k, v in body.model_dump().items():
        setattr(tenant, k, v)
    db.commit()
    db.refresh(tenant)
    after = snapshot_row(tenant, _TENANT_FIELDS)
    diff_before = {k: v for k, v in before.items() if before.get(k) != after.get(k)}
    if diff_before:
        log_event(
            db, user, action="update", entity_type="tenant",
            entity_id=str(tenant.id), entity_label=_tenant_label(tenant),
            before=diff_before,
            after={k: after.get(k) for k in diff_before},
        )
    return tenant


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(tenant_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Locataire introuvable")
    if not has_global_access(user):
        accessible = accessible_property_ids(db, user) or set()
        linked = _tenant_linked_property_ids(db, tenant_id)
        # Visibility gate
        if linked and not (linked & accessible):
            raise HTTPException(404, "Locataire introuvable")
        # Deletion gate: must have access to ALL linked properties
        if linked - accessible:
            raise HTTPException(403, "Suppression interdite — ce locataire est lié à des biens hors de votre périmètre")
    before = snapshot_row(tenant, _TENANT_FIELDS)
    label = _tenant_label(tenant)
    db.delete(tenant)
    db.commit()
    log_event(
        db, user, action="delete", entity_type="tenant",
        entity_id=str(tenant_id), entity_label=label, before=before,
    )

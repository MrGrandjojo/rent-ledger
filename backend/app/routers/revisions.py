from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..audit_log import log_event, snapshot_row
from ..database import get_db
from ..dependencies import assert_lease_access, get_current_user
from ..models import Lease, Property, RentRevision, Tenant, User
from ..schemas import RentRevisionCreate, RentRevisionOut

router = APIRouter(prefix="/api/leases", tags=["rent-revisions"])

_REVISION_FIELDS = [
    "id", "lease_id", "effective_from", "monthly_rent",
    "monthly_charges", "reason",
]


def _revision_label(db: Session, rev: RentRevision) -> str:
    lease = db.get(Lease, rev.lease_id)
    if lease is None:
        return f"Révision #{rev.id}"
    prop = db.get(Property, lease.property_id)
    tenant = db.get(Tenant, lease.tenant_id)
    parts = []
    if prop: parts.append(prop.name)
    if tenant: parts.append(f"{tenant.last_name} {tenant.first_name}".strip())
    parts.append(rev.effective_from.isoformat())
    return " / ".join(parts)


@router.get("/{lease_id}/revisions", response_model=list[RentRevisionOut])
def list_revisions(lease_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_lease_access(db, user, lease_id)
    return (
        db.query(RentRevision)
        .filter(RentRevision.lease_id == lease_id)
        .order_by(RentRevision.effective_from.desc())
        .all()
    )


@router.post("/{lease_id}/revisions", response_model=RentRevisionOut, status_code=201)
def create_revision(
    lease_id: int,
    body: RentRevisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_lease_access(db, user, lease_id)
    existing = db.query(RentRevision).filter_by(
        lease_id=lease_id, effective_from=body.effective_from
    ).first()
    if existing:
        raise HTTPException(409, "Une révision existe déjà pour cette date")
    rev = RentRevision(lease_id=lease_id, **body.model_dump())
    db.add(rev)
    db.commit()
    db.refresh(rev)
    log_event(
        db, user, action="create", entity_type="rent_revision",
        entity_id=str(rev.id), entity_label=_revision_label(db, rev),
        after=snapshot_row(rev, _REVISION_FIELDS),
    )
    return rev


@router.delete("/{lease_id}/revisions/{rev_id}", status_code=204)
def delete_revision(
    lease_id: int,
    rev_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_lease_access(db, user, lease_id)
    rev = db.get(RentRevision, rev_id)
    if not rev or rev.lease_id != lease_id:
        raise HTTPException(404, "Révision introuvable")
    if rev.reason == "initial":
        raise HTTPException(400, "La révision initiale ne peut pas être supprimée")
    before = snapshot_row(rev, _REVISION_FIELDS)
    label = _revision_label(db, rev)
    db.delete(rev)
    db.commit()
    log_event(
        db, user, action="delete", entity_type="rent_revision",
        entity_id=str(rev_id), entity_label=label, before=before,
    )

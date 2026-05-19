from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..audit_log import log_event, snapshot_row
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_lease_access, assert_property_access,
    get_current_user,
)
from ..lease_rules import (
    compute_end_date, compute_next_irl_revision, compute_renewed_end_date,
    current_effective_revision, initial_revision_for, is_amendment,
    notice_period_alert, resolve_end_date, upsert_initial_revision,
)
from ..models import Lease, Property, Tenant, User
from ..schemas import LeaseCreate, LeaseDetailOut, LeaseOut, LeaseSummary, LeaseUpdate

router = APIRouter(prefix="/api/leases", tags=["leases"])

_LEASE_FIELDS = [
    "id", "property_id", "tenant_id", "parent_lease_id", "lease_type",
    "start_date", "end_date", "security_deposit_amount",
    "security_deposit_date", "is_active",
]


def _lease_label(db: Session, lease: Lease) -> str:
    prop = db.get(Property, lease.property_id)
    tenant = db.get(Tenant, lease.tenant_id)
    parts = []
    if prop: parts.append(prop.name)
    if tenant: parts.append(f"{tenant.first_name} {tenant.last_name}".strip())
    return " / ".join(parts) or f"Bail #{lease.id}"


def _apply_tacit_renewal(lease: Lease, db: Session) -> None:
    """If today > end_date and the lease is active, roll end_date forward by
    one default duration. Only applies to parent / stand-alone leases —
    amendments inherit end_date from their parent."""
    if is_amendment(lease):
        return
    today = date.today()
    if lease.is_active and lease.end_date and today > lease.end_date:
        new_end = compute_renewed_end_date(
            lease.start_date, lease.lease_type, lease.end_date, today
        )
        if new_end != lease.end_date:
            lease.end_date = new_end
            db.commit()
            db.refresh(lease)


def _summary(lease: Lease, db: Session) -> LeaseSummary:
    tenant = db.get(Tenant, lease.tenant_id)
    cur_rev = current_effective_revision(db, lease.id, date.today())
    total = (Decimal(cur_rev.monthly_rent) + Decimal(cur_rev.monthly_charges)) if cur_rev else None
    return LeaseSummary(
        id=lease.id,
        tenant_first_name=tenant.first_name if tenant else "",
        tenant_last_name=tenant.last_name if tenant else "",
        start_date=lease.start_date,
        end_date=resolve_end_date(lease, db),
        current_monthly_total=total,
        is_active=lease.is_active,
    )


def _enrich(lease: Lease, db: Session, *, include_property_tenant: bool) -> dict:
    today = date.today()
    d = {c.name: getattr(lease, c.name) for c in lease.__table__.columns}
    d["is_amendment"] = is_amendment(lease)
    d["end_date"] = resolve_end_date(lease, db, today)
    d["next_irl_revision_date"] = compute_next_irl_revision(lease.start_date, today)
    d["notice_period_open"] = notice_period_alert(lease, d["end_date"], today)

    initial = initial_revision_for(db, lease.id)
    if initial is not None:
        d["initial_monthly_rent"] = Decimal(initial.monthly_rent)
        d["initial_monthly_charges"] = Decimal(initial.monthly_charges)
        d["initial_monthly_total"] = (
            Decimal(initial.monthly_rent) + Decimal(initial.monthly_charges)
        )
    current = current_effective_revision(db, lease.id, today)
    if current is not None:
        d["current_monthly_rent"] = Decimal(current.monthly_rent)
        d["current_monthly_charges"] = Decimal(current.monthly_charges)
        d["current_monthly_total"] = (
            Decimal(current.monthly_rent) + Decimal(current.monthly_charges)
        )

    if include_property_tenant:
        d["property"] = db.get(Property, lease.property_id)
        d["tenant"] = db.get(Tenant, lease.tenant_id)
        parent = db.get(Lease, lease.parent_lease_id) if lease.parent_lease_id else None
        d["parent_lease"] = _summary(parent, db) if parent else None
        children = (
            db.query(Lease)
            .filter(Lease.parent_lease_id == lease.id)
            .order_by(Lease.start_date.asc())
            .all()
        )
        d["amendments"] = [_summary(c, db) for c in children]
    return d


def _validate_amendment(body: LeaseCreate | LeaseUpdate, db: Session, self_id: int | None) -> Lease | None:
    """Return the parent Lease if `body.parent_lease_id` is set, raising on
    inconsistencies (parent must exist, be on the same property, not be self,
    and itself not be an amendment)."""
    if body.parent_lease_id is None:
        return None
    if self_id is not None and body.parent_lease_id == self_id:
        raise HTTPException(400, "Un bail ne peut pas être avenant de lui-même")
    parent = db.get(Lease, body.parent_lease_id)
    if parent is None:
        raise HTTPException(404, "Bail parent introuvable")
    if parent.property_id != body.property_id:
        raise HTTPException(400, "Le bail parent doit porter sur le même bien")
    if parent.parent_lease_id is not None:
        raise HTTPException(400, "Un avenant ne peut pas avoir d'avenant")
    return parent


@router.get("", response_model=list[LeaseDetailOut])
def list_leases(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Lease)
    ids = accessible_property_ids(db, user)
    if ids is not None:
        if not ids:
            return []
        q = q.filter(Lease.property_id.in_(ids))
    leases = q.order_by(Lease.start_date.desc()).all()
    for l in leases:
        _apply_tacit_renewal(l, db)
    return [_enrich(l, db, include_property_tenant=True) for l in leases]


@router.post("", response_model=LeaseDetailOut, status_code=201)
def create_lease(body: LeaseCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Property-access check first — also covers the 404 for non-existent.
    assert_property_access(db, user, body.property_id)
    if not db.get(Tenant, body.tenant_id):
        raise HTTPException(404, "Locataire introuvable")

    parent = _validate_amendment(body, db, self_id=None)

    # Amendments inherit lease_type from the parent
    lease_type = parent.lease_type if parent else body.lease_type
    # Amendments inherit end_date from the parent at write time too — the
    # authoritative read goes through resolve_end_date and follows the parent
    # going forward.
    end_date = parent.end_date if parent else compute_end_date(body.start_date, lease_type)

    lease = Lease(
        property_id=body.property_id,
        tenant_id=body.tenant_id,
        parent_lease_id=body.parent_lease_id,
        lease_type=lease_type,
        start_date=body.start_date,
        end_date=end_date,
        security_deposit_amount=body.security_deposit_amount,
        security_deposit_date=body.security_deposit_date,
        is_active=body.is_active,
    )
    db.add(lease)
    db.flush()
    # Initial rent_revision — single source of truth for rent on this lease.
    upsert_initial_revision(
        db, lease.id, lease.start_date,
        Decimal(body.monthly_rent), Decimal(body.monthly_charges),
    )
    db.commit()
    db.refresh(lease)
    after = snapshot_row(lease, _LEASE_FIELDS)
    after["monthly_rent"] = str(Decimal(body.monthly_rent))
    after["monthly_charges"] = str(Decimal(body.monthly_charges))
    log_event(
        db, user, action="create", entity_type="lease",
        entity_id=str(lease.id), entity_label=_lease_label(db, lease),
        after=after,
    )
    return _enrich(lease, db, include_property_tenant=True)


@router.get("/{lease_id}", response_model=LeaseDetailOut)
def get_lease(lease_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lease = assert_lease_access(db, user, lease_id)
    _apply_tacit_renewal(lease, db)
    return _enrich(lease, db, include_property_tenant=True)


@router.put("/{lease_id}", response_model=LeaseDetailOut)
def update_lease(lease_id: int, body: LeaseUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lease = assert_lease_access(db, user, lease_id)
    # If the user is reassigning to a different property, they must be able to
    # access the new property too.
    if body.property_id != lease.property_id:
        assert_property_access(db, user, body.property_id)

    parent = _validate_amendment(body, db, self_id=lease_id)

    before_full = snapshot_row(lease, _LEASE_FIELDS)
    initial_rev = initial_revision_for(db, lease.id)
    if initial_rev is not None:
        before_full["monthly_rent"] = str(Decimal(initial_rev.monthly_rent))
        before_full["monthly_charges"] = str(Decimal(initial_rev.monthly_charges))

    lease.property_id = body.property_id
    lease.tenant_id = body.tenant_id
    lease.parent_lease_id = body.parent_lease_id
    lease.lease_type = parent.lease_type if parent else body.lease_type
    lease.start_date = body.start_date
    lease.end_date = (
        parent.end_date if parent
        else compute_end_date(body.start_date, lease.lease_type)
    )
    lease.security_deposit_amount = body.security_deposit_amount
    lease.security_deposit_date = body.security_deposit_date
    lease.is_active = body.is_active

    # Keep the initial rent_revision in sync with the lease form's rent fields.
    upsert_initial_revision(
        db, lease.id, lease.start_date,
        Decimal(body.monthly_rent), Decimal(body.monthly_charges),
    )
    db.commit()
    db.refresh(lease)

    after_full = snapshot_row(lease, _LEASE_FIELDS)
    after_full["monthly_rent"] = str(Decimal(body.monthly_rent))
    after_full["monthly_charges"] = str(Decimal(body.monthly_charges))
    diff_before = {k: v for k, v in before_full.items() if before_full.get(k) != after_full.get(k)}
    diff_after = {k: after_full.get(k) for k in diff_before.keys()}
    if diff_before:
        log_event(
            db, user, action="update", entity_type="lease",
            entity_id=str(lease.id), entity_label=_lease_label(db, lease),
            before=diff_before, after=diff_after,
        )
    return _enrich(lease, db, include_property_tenant=True)


@router.delete("/{lease_id}", status_code=204)
def delete_lease(lease_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lease = assert_lease_access(db, user, lease_id)
    has_children = db.query(Lease).filter(Lease.parent_lease_id == lease_id).first()
    if has_children:
        raise HTTPException(409, "Ce bail a des avenants — supprimez-les d'abord")
    before = snapshot_row(lease, _LEASE_FIELDS)
    label = _lease_label(db, lease)
    db.delete(lease)
    db.commit()
    log_event(
        db, user, action="delete", entity_type="lease",
        entity_id=str(lease_id), entity_label=label, before=before,
    )

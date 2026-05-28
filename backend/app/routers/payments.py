from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..audit_log import log_event, snapshot_row
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_lease_access, get_current_user,
    has_global_access, require_admin_or_supervisor,
)
from ..lease_rules import effective_revision_for, expected_amount_for
from ..models import Lease, Payment, Property, Tenant, User
from ..schemas import (
    BulkPaymentCreate, BulkPaymentPreviewOut, BulkPaymentPreviewRow,
    BulkPaymentResult, ExpectedAmountOut, PaginatedPaymentsOut,
    PaymentCreate, PaymentOut, PaymentUpdate,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])

_PAYMENT_FIELDS = [
    "id", "lease_id", "year", "month", "expected_amount",
    "received_amount", "payment_date", "status", "outstanding_balance",
    "notes",
]


def _payment_label(db: Session, payment: Payment) -> str:
    lease = db.get(Lease, payment.lease_id)
    if lease is None:
        return f"Paiement #{payment.id}"
    prop = db.get(Property, lease.property_id)
    tenant = db.get(Tenant, lease.tenant_id)
    parts = []
    if prop: parts.append(prop.name)
    if tenant: parts.append(f"{tenant.last_name} {tenant.first_name}".strip())
    parts.append(f"{payment.month:02d}/{payment.year}")
    return " / ".join(parts)


def _compute_status(expected: Decimal, received: Decimal) -> tuple[str, Decimal]:
    diff = expected - received
    if diff <= 0:
        return "paid", Decimal("0")
    elif received > 0:
        return "partial", diff
    else:
        return "unpaid", diff


@router.get("/expected", response_model=ExpectedAmountOut)
def get_expected_amount(
    lease_id: int = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the expected monthly amount for (lease, year, month) using the
    rent_revision in effect at the first day of that month. Used by the
    payment form to auto-fill the 'Montant attendu' field — recomputed each
    time the user changes the year/month selector."""
    assert_lease_access(db, user, lease_id)
    if not (1 <= month <= 12):
        raise HTTPException(400, "Mois invalide")
    rev = effective_revision_for(db, lease_id, year, month)
    if rev is None:
        raise HTTPException(
            500, "Aucune révision de loyer pour ce bail — incohérence de données"
        )
    return ExpectedAmountOut(
        lease_id=lease_id, year=year, month=month,
        expected_amount=Decimal(rev.monthly_rent) + Decimal(rev.monthly_charges),
        monthly_rent=Decimal(rev.monthly_rent),
        monthly_charges=Decimal(rev.monthly_charges),
        revision_effective_from=rev.effective_from,
    )


@router.get("", response_model=PaginatedPaymentsOut)
def list_payments(
    lease_id: int | None = None,
    year: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paginated listing — see PaginatedPaymentsOut. At PME scale (~1000
    baux × 12 months × multiple years), an unpaginated GET would return
    tens of thousands of rows; the envelope shape forces every consumer
    to handle pagination explicitly. `year` filter is server-side so the
    frontend can narrow before paging.

    The join on Property/Tenant is always present so the secondary sort
    (within a (year, month) bucket → by property name then tenant name)
    is stable across requests."""
    q = (
        db.query(Payment)
        .join(Lease, Lease.id == Payment.lease_id)
        .join(Property, Property.id == Lease.property_id)
        .join(Tenant, Tenant.id == Lease.tenant_id)
    )
    if lease_id is not None:
        assert_lease_access(db, user, lease_id)
        q = q.filter(Payment.lease_id == lease_id)
    else:
        ids = accessible_property_ids(db, user)
        if ids is not None:
            if not ids:
                return PaginatedPaymentsOut(items=[], total=0, page=page, page_size=page_size)
            q = q.filter(Lease.property_id.in_(ids))
    if year is not None:
        q = q.filter(Payment.year == year)

    total = q.count()
    items = (
        q.order_by(
            Payment.year.desc(),
            Payment.month.desc(),
            Property.name.asc(),
            Tenant.last_name.asc(),
            Tenant.first_name.asc(),
            Payment.lease_id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedPaymentsOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=PaymentOut, status_code=201)
def create_payment(body: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lease = assert_lease_access(db, user, body.lease_id)
    existing = db.query(Payment).filter_by(
        lease_id=body.lease_id, year=body.year, month=body.month
    ).first()
    if existing:
        raise HTTPException(409, "Un paiement existe déjà pour cette période")
    # Trust client-provided expected_amount only as a fallback. The
    # authoritative value is the rent_revision in effect for the period.
    expected = expected_amount_for(db, lease, body.year, body.month)
    status, outstanding = _compute_status(expected, body.received_amount)
    payment = Payment(
        lease_id=body.lease_id,
        year=body.year,
        month=body.month,
        expected_amount=expected,
        received_amount=body.received_amount,
        payment_date=body.payment_date,
        notes=body.notes,
        status=status,
        outstanding_balance=outstanding,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    log_event(
        db, user, action="create", entity_type="payment",
        entity_id=str(payment.id), entity_label=_payment_label(db, payment),
        after=snapshot_row(payment, _PAYMENT_FIELDS),
    )
    return payment


def _payment_visible(db: Session, user: User, payment: Payment) -> bool:
    if has_global_access(user):
        return True
    ids = accessible_property_ids(db, user) or set()
    lease = db.get(Lease, payment.lease_id)
    return bool(lease and lease.property_id in ids)


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Payment, payment_id)
    if not p or not _payment_visible(db, user, p):
        raise HTTPException(404, "Paiement introuvable")
    return p


@router.put("/{payment_id}", response_model=PaymentOut)
def update_payment(payment_id: int, body: PaymentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Payment, payment_id)
    if not p or not _payment_visible(db, user, p):
        raise HTTPException(404, "Paiement introuvable")
    before = {
        "received_amount": str(Decimal(p.received_amount)),
        "status": p.status,
        "outstanding_balance": str(Decimal(p.outstanding_balance)),
    }
    p.received_amount = body.received_amount
    p.payment_date = body.payment_date
    p.notes = body.notes
    p.status, p.outstanding_balance = _compute_status(p.expected_amount, body.received_amount)
    db.commit()
    db.refresh(p)
    after = {
        "received_amount": str(Decimal(p.received_amount)),
        "status": p.status,
        "outstanding_balance": str(Decimal(p.outstanding_balance)),
    }
    log_event(
        db, user, action="update", entity_type="payment",
        entity_id=str(p.id), entity_label=_payment_label(db, p),
        before=before, after=after,
    )
    return p


@router.delete("/{payment_id}", status_code=204)
def delete_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_supervisor),
):
    """Suppression réservée à admin/supervisor — un bailleur (role=user)
    peut éditer ses paiements mais pas les supprimer (perte d'historique
    + cohérence des soldes cumulés)."""
    p = db.get(Payment, payment_id)
    if not p or not _payment_visible(db, user, p):
        raise HTTPException(404, "Paiement introuvable")
    before = snapshot_row(p, _PAYMENT_FIELDS)
    label = _payment_label(db, p)
    db.delete(p)
    db.commit()
    log_event(
        db, user, action="delete", entity_type="payment",
        entity_id=str(payment_id), entity_label=label, before=before,
    )


# ── Bulk entry (retroactive months) ───────────────────────────────────────────

def _iter_months(y1: int, m1: int, y2: int, m2: int):
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        yield y, m
        if m == 12:
            y += 1; m = 1
        else:
            m += 1


@router.get("/bulk/preview", response_model=BulkPaymentPreviewOut)
def preview_bulk(
    lease_id: int = Query(...),
    from_year: int = Query(...),
    from_month: int = Query(..., ge=1, le=12),
    to_year: int = Query(...),
    to_month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return one row per month in the requested range, with the expected
    amount derived from the rent_revision in effect for that month and a
    flag indicating whether a Payment record already exists. The frontend
    uses this to render the per-row checklist of Step 4."""
    lease = assert_lease_access(db, user, lease_id)
    if (from_year, from_month) > (to_year, to_month):
        raise HTTPException(400, "Plage de dates invalide")
    existing = {
        (p.year, p.month) for p in
        db.query(Payment.year, Payment.month).filter(Payment.lease_id == lease_id).all()
    }
    rows: list[BulkPaymentPreviewRow] = []
    for y, m in _iter_months(from_year, from_month, to_year, to_month):
        rev = effective_revision_for(db, lease.id, y, m)
        expected = (
            Decimal(rev.monthly_rent) + Decimal(rev.monthly_charges)
            if rev is not None else Decimal("0")
        )
        rows.append(BulkPaymentPreviewRow(
            year=y, month=m, expected_amount=expected,
            has_existing=(y, m) in existing,
        ))
    return BulkPaymentPreviewOut(lease_id=lease_id, rows=rows)


@router.post("/bulk", response_model=BulkPaymentResult, status_code=201)
def create_bulk(
    body: BulkPaymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create one Payment record per requested (year, month) row.

    The expected_amount for each row is always derived server-side from the
    rent_revision in effect at the first day of that month — never trusted
    from the client. A month that already has a payment is rejected for the
    whole batch (HTTP 409) so partial inserts cannot happen on retry.
    """
    lease = assert_lease_access(db, user, body.lease_id)
    if not body.rows:
        raise HTTPException(400, "Aucune période sélectionnée")

    # Reject duplicates inside the body too.
    seen = set()
    for r in body.rows:
        key = (r.year, r.month)
        if key in seen:
            raise HTTPException(400, f"Doublon dans la requête : {r.month:02d}/{r.year}")
        seen.add(key)
        if not (1 <= r.month <= 12):
            raise HTTPException(400, f"Mois invalide : {r.month}")

    existing = {
        (p.year, p.month) for p in
        db.query(Payment.year, Payment.month)
        .filter(Payment.lease_id == body.lease_id).all()
    }
    conflicts = sorted(seen & existing)
    if conflicts:
        raise HTTPException(
            409,
            "Paiement déjà saisi pour : "
            + ", ".join(f"{m:02d}/{y}" for y, m in conflicts),
        )

    created: list[Payment] = []
    total_expected = Decimal("0")
    total_received = Decimal("0")
    total_outstanding = Decimal("0")

    for r in body.rows:
        expected = expected_amount_for(db, lease, r.year, r.month)
        received = Decimal(r.received_amount or 0)
        status_v, outstanding = _compute_status(expected, received)
        notes = (r.notes or "Saisie rétroactive").strip()
        payment = Payment(
            lease_id=body.lease_id,
            year=r.year, month=r.month,
            expected_amount=expected,
            received_amount=received,
            payment_date=None,
            notes=notes,
            status=status_v,
            outstanding_balance=outstanding,
        )
        db.add(payment)
        created.append(payment)
        total_expected += expected
        total_received += received
        total_outstanding += outstanding

    db.commit()
    for payment in created:
        db.refresh(payment)
        snapshot = snapshot_row(payment, _PAYMENT_FIELDS)
        snapshot["origin"] = "bulk"
        log_event(
            db, user, action="create", entity_type="payment",
            entity_id=str(payment.id),
            entity_label=_payment_label(db, payment),
            after=snapshot,
        )

    return BulkPaymentResult(
        created_count=len(created),
        total_expected=total_expected,
        total_received=total_received,
        total_outstanding=total_outstanding,
        payments=created,
    )

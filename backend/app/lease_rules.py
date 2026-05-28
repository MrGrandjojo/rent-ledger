"""Domain rules for lease lifecycle and rent revisions.

`rent_revisions` is the single source of truth for monthly rent and charges.
No other code path should read rent values from the `leases` table.
"""

from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from .models import Lease, RentRevision


# Default lease duration (in months) and landlord notice period (in months) per type.
LEASE_TYPE_RULES = {
    "unfurnished":       {"duration_months": 36, "notice_months": 6},
    "furnished":         {"duration_months": 12, "notice_months": 3},
    "furnished_student": {"duration_months": 9,  "notice_months": 3},
}


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    from calendar import monthrange
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def compute_end_date(start_date: date, lease_type: str) -> date:
    """Initial end_date = start_date + default duration for lease_type."""
    months = LEASE_TYPE_RULES.get(lease_type, LEASE_TYPE_RULES["unfurnished"])["duration_months"]
    return _add_months(start_date, months)


def compute_renewed_end_date(start_date: date, lease_type: str, current_end: date, today: date) -> date:
    """Roll end_date forward by one default duration each time it's reached
    (tacit renewal) until the new end_date is after today."""
    rule = LEASE_TYPE_RULES.get(lease_type, LEASE_TYPE_RULES["unfurnished"])
    months = rule["duration_months"]
    new_end = current_end
    while new_end < today:
        new_end = _add_months(new_end, months)
    return new_end


def compute_next_irl_revision(start_date: date, today: date) -> date:
    """Next anniversary of start_date in the future (within 12 months)."""
    candidate = date(today.year, start_date.month, min(start_date.day, 28))
    if candidate <= today:
        candidate = date(today.year + 1, start_date.month, min(start_date.day, 28))
    return candidate


def notice_period_alert(lease: Lease, end_date: Optional[date], today: date) -> bool:
    """True if today is within the landlord notice period of end_date."""
    if not end_date:
        return False
    notice_months = LEASE_TYPE_RULES.get(
        lease.lease_type, LEASE_TYPE_RULES["unfurnished"]
    )["notice_months"]
    threshold = _add_months(end_date, -notice_months)
    return threshold <= today <= end_date


# ── Amendments (avenants) ─────────────────────────────────────────────────────

def is_amendment(lease: Lease) -> bool:
    return lease.parent_lease_id is not None


def resolve_end_date(lease: Lease, db: Session, today: Optional[date] = None) -> Optional[date]:
    """Return the authoritative end_date for a lease.

    Parent leases (or stand-alone leases): use the stored `end_date`,
    rolled forward by tacit renewal if needed (caller persists the change).

    Amendments: always return the *current* end_date of the parent lease.
    Stored `end_date` on the child is a denormalised copy that may lag
    behind the parent — never trust it for reads.
    """
    if today is None:
        today = date.today()
    if is_amendment(lease):
        parent = db.get(Lease, lease.parent_lease_id)
        if parent is None:
            return lease.end_date
        return resolve_end_date(parent, db, today)
    return lease.end_date


def resolve_lease_type(lease: Lease, db: Session) -> str:
    """Amendments inherit lease_type from their parent."""
    if is_amendment(lease):
        parent = db.get(Lease, lease.parent_lease_id)
        if parent is not None:
            return parent.lease_type
    return lease.lease_type


# ── Rent revisions ────────────────────────────────────────────────────────────

def initial_revision_for(db: Session, lease_id: int) -> Optional[RentRevision]:
    """Return the revision tagged reason='initial' for the lease.
    Falls back to the chronologically first revision if no row is tagged
    'initial' (defensive — every lease should have an initial)."""
    rev = (
        db.query(RentRevision)
        .filter(RentRevision.lease_id == lease_id, RentRevision.reason == "initial")
        .order_by(RentRevision.effective_from.asc())
        .first()
    )
    if rev is not None:
        return rev
    return (
        db.query(RentRevision)
        .filter(RentRevision.lease_id == lease_id)
        .order_by(RentRevision.effective_from.asc())
        .first()
    )


def effective_revision_for(
    db: Session, lease_id: int, year: int, month: int
) -> Optional[RentRevision]:
    """Return the revision with the latest effective_from <= the first day of
    (year, month) for the given lease."""
    target = date(year, month, 1)
    return (
        db.query(RentRevision)
        .filter(RentRevision.lease_id == lease_id)
        .filter(RentRevision.effective_from <= target)
        .order_by(RentRevision.effective_from.desc())
        .first()
    )


def expected_amount_for(db: Session, lease: Lease, year: int, month: int) -> Decimal:
    """Expected total (rent + charges) for (lease, year, month), from the
    rent_revision in effect at the first day of that month.
    Raises if no revision exists at all — this signals a data integrity issue
    that must be fixed at the source, not papered over."""
    rev = effective_revision_for(db, lease.id, year, month)
    if rev is None:
        rev = initial_revision_for(db, lease.id)
        if rev is None:
            raise RuntimeError(
                f"Lease {lease.id} has no rent_revision — data integrity violation"
            )
    return Decimal(rev.monthly_rent) + Decimal(rev.monthly_charges)


def current_effective_revision(db: Session, lease_id: int, today: date) -> Optional[RentRevision]:
    return effective_revision_for(db, lease_id, today.year, today.month)


def batch_effective_revisions(
    db: Session, lease_ids: list[int], target_date: date,
) -> dict[int, RentRevision]:
    """Return `{lease_id: RentRevision}` mapping each lease to the
    revision in effect at `target_date` (largest effective_from ≤ target).

    Single round-trip — used by hot paths (dashboard, leases list) where
    calling `effective_revision_for` per lease would cause an N+1 storm at
    PME scale (1000 baux → 1000 queries per page load)."""
    if not lease_ids:
        return {}
    rows = (
        db.query(RentRevision)
        .filter(
            RentRevision.lease_id.in_(lease_ids),
            RentRevision.effective_from <= target_date,
        )
        .order_by(RentRevision.lease_id, RentRevision.effective_from.desc())
        .all()
    )
    result: dict[int, RentRevision] = {}
    for r in rows:
        # First row per lease_id wins thanks to the descending order.
        if r.lease_id not in result:
            result[r.lease_id] = r
    return result


def batch_initial_revisions(
    db: Session, lease_ids: list[int],
) -> dict[int, RentRevision]:
    """Return `{lease_id: RentRevision}` for the initial revision of each
    lease. Same purpose as `batch_effective_revisions` — kills the N+1 in
    the leases list endpoint."""
    if not lease_ids:
        return {}
    rows = (
        db.query(RentRevision)
        .filter(RentRevision.lease_id.in_(lease_ids))
        .order_by(
            RentRevision.lease_id,
            # 'initial' rows first, then chronological fallback.
            (RentRevision.reason == "initial").desc(),
            RentRevision.effective_from.asc(),
        )
        .all()
    )
    result: dict[int, RentRevision] = {}
    for r in rows:
        if r.lease_id not in result:
            result[r.lease_id] = r
    return result


def upsert_initial_revision(
    db: Session, lease_id: int, start_date: date,
    monthly_rent: Decimal, monthly_charges: Decimal,
) -> RentRevision:
    """Set the lease's `initial` revision to the given rent/charges. Creates
    one with effective_from = start_date if none exists. Updates the existing
    one in place otherwise (preserving its effective_from)."""
    rev = initial_revision_for(db, lease_id)
    if rev is None:
        rev = RentRevision(
            lease_id=lease_id, effective_from=start_date,
            monthly_rent=monthly_rent, monthly_charges=monthly_charges,
            reason="initial",
        )
        db.add(rev)
    else:
        rev.monthly_rent = monthly_rent
        rev.monthly_charges = monthly_charges
        rev.reason = "initial"
    return rev

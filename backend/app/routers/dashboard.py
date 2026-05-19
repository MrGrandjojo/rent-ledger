from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import accessible_property_ids, get_current_user
from ..lease_rules import (
    compute_next_irl_revision, current_effective_revision,
    expected_amount_for, notice_period_alert, resolve_end_date,
)
from ..models import Lease, Payment, Property, Tenant, User
from ..schemas import DashboardOut, DashboardStats, LeaseRow

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

IRL_ALERT_DAYS = 30


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = date.today()
    current_year = today.year
    current_month = today.month

    accessible = accessible_property_ids(db, user)
    prop_q = db.query(Property)
    lease_q = db.query(Lease).filter(Lease.is_active == True)  # noqa: E712
    if accessible is not None:
        if not accessible:
            return DashboardOut(
                stats=DashboardStats(
                    properties_total=0, active_leases=0,
                    current_month_paid=0, current_month_partial=0, current_month_unpaid=0,
                    total_expected=Decimal("0"), total_received=Decimal("0"),
                    total_outstanding_current_month=Decimal("0"),
                    total_outstanding_all_months=Decimal("0"),
                    total_outstanding=Decimal("0"),
                ),
                rows=[],
            )
        prop_q = prop_q.filter(Property.id.in_(accessible))
        lease_q = lease_q.filter(Lease.property_id.in_(accessible))

    properties = prop_q.order_by(Property.name).all()
    active_leases = lease_q.all()

    # Group active leases by property_id (may be >1)
    leases_by_property: dict[int, list[Lease]] = {}
    for lease in active_leases:
        leases_by_property.setdefault(lease.property_id, []).append(lease)

    # Index every payment of every active lease — we need both unpaid
    # AND overpaid rows because an overpayment (received > expected)
    # must reduce the all-months total like a payment toward an arrears
    # month would (e.g. ROMY-LEFÈVRE pays 618 € for one 515 € month, the
    # 103 € surplus credits down his cumulative debt).
    active_lease_ids = [l.id for l in active_leases]
    all_lease_payments: list[Payment] = (
        db.query(Payment)
        .filter(Payment.lease_id.in_(active_lease_ids))
        .all()
    ) if active_lease_ids else []

    payments_by_lease: dict[int, list[Payment]] = {lid: [] for lid in active_lease_ids}
    payments_this_month: list[Payment] = []
    payment_by_lease: dict[int, Payment] = {}
    for p in all_lease_payments:
        payments_by_lease.setdefault(p.lease_id, []).append(p)
        if p.year == current_year and p.month == current_month:
            payments_this_month.append(p)
            payment_by_lease[p.lease_id] = p

    rows: list[LeaseRow] = []

    for prop in properties:
        prop_address = f"{prop.address_street}, {prop.address_zip} {prop.address_city}"
        leases_here = leases_by_property.get(prop.id, [])
        if not leases_here:
            # Vacant — still appear as one row.
            rows.append(LeaseRow(
                property_id=prop.id,
                property_name=prop.name,
                property_type=prop.type,
                address=prop_address,
            ))
            continue

        for lease in leases_here:
            tenant = db.get(Tenant, lease.tenant_id)
            tenant_name = f"{tenant.first_name} {tenant.last_name}" if tenant else None

            # Current effective rent — rent_revisions is sole source of truth
            rev = current_effective_revision(db, lease.id, today)
            if rev is None:
                # Defensive — should never happen (every lease has an initial)
                rent = charges = Decimal("0")
            else:
                rent = Decimal(rev.monthly_rent)
                charges = Decimal(rev.monthly_charges)
            total = rent + charges

            # Alerts (amendments inherit end_date from their parent)
            effective_end = resolve_end_date(lease, db, today)
            next_irl = compute_next_irl_revision(lease.start_date, today)
            irl_alert = 0 <= (next_irl - today).days <= IRL_ALERT_DAYS
            notice_alert = notice_period_alert(lease, effective_end, today)

            # Current-month payment. Per v2.3, the dashboard considers
            # the current month due from day one — if no Payment row
            # exists, we project it as `status=unpaid, outstanding=expected`
            # so the landlord sees the upcoming rent as part of the debt
            # immediately. The scheduler does NOT write the unpaid row
            # until the month is over (see `scheduler.run_catch_up`).
            payment = payment_by_lease.get(lease.id)
            expected_this_month = expected_amount_for(db, lease, current_year, current_month)
            if payment:
                payment_info = {
                    "status": payment.status,
                    "expected": float(payment.expected_amount),
                    "received": float(payment.received_amount),
                    "outstanding": float(payment.outstanding_balance),
                }
                outstanding = Decimal(payment.outstanding_balance)
            else:
                payment_info = {
                    "status": "unpaid",
                    "expected": float(expected_this_month),
                    "received": 0.0,
                    "outstanding": float(expected_this_month),
                }
                outstanding = expected_this_month

            # All-months outstanding — net of overpayments.
            #     total = max(0, Σ expected - Σ received)
            # over every Payment row of this lease, plus the current month
            # if missing (projected as expected, received 0). This is the
            # only formula that correctly applies an overpayment on month M
            # against an arrears month — the per-row `outstanding_balance`
            # clamps at 0 and would lose the credit.
            lease_payments = payments_by_lease.get(lease.id, [])
            sum_expected = sum((Decimal(p.expected_amount) for p in lease_payments), Decimal("0"))
            sum_received = sum((Decimal(p.received_amount) for p in lease_payments), Decimal("0"))
            if payment is None:
                sum_expected = sum_expected + expected_this_month
            outstanding_total = max(Decimal("0"), sum_expected - sum_received)

            # Count of months still owed money. Per v2.3, the current
            # month without a record counts as 1 owed month.
            outstanding_months = sum(
                1 for p in lease_payments if Decimal(p.outstanding_balance) > 0
            )
            if payment is None and expected_this_month > 0:
                outstanding_months += 1

            overdue_alert = outstanding > 0

            rows.append(LeaseRow(
                property_id=prop.id,
                property_name=prop.name,
                property_type=prop.type,
                address=prop_address,
                lease_id=lease.id,
                tenant_name=tenant_name,
                monthly_rent=rent,
                monthly_charges=charges,
                monthly_total=total,
                current_payment=payment_info,
                outstanding=outstanding,
                outstanding_total=outstanding_total,
                outstanding_months_count=outstanding_months,
                irl_alert=irl_alert,
                notice_alert=notice_alert,
                overdue_alert=overdue_alert,
            ))

    # Stats — based on active leases (one row per lease). Per v2.3, a
    # lease with NO current-month record IS counted as unpaid in the
    # dashboard view from day one of the month — the scheduler simply
    # doesn't write the row until the month is over.
    paid = sum(1 for p in payments_this_month if p.status == "paid")
    partial = sum(1 for p in payments_this_month if p.status == "partial")
    unpaid_explicit = sum(1 for p in payments_this_month if p.status == "unpaid")
    unpaid_missing = len(active_lease_ids) - len(payments_this_month)
    unpaid_count = unpaid_explicit + unpaid_missing

    # Expected total for the current month — sum every active lease's
    # expected. Useful to compute the "loyers attendus" figure even if
    # no payment row exists yet for some leases.
    total_expected = sum(
        (expected_amount_for(db, l, current_year, current_month) for l in active_leases),
        Decimal("0"),
    )
    total_received = sum((Decimal(p.received_amount) for p in payments_this_month), Decimal("0"))
    # Per v2.3 dashboard semantics, the current month is projected as
    # unpaid (expected amount) for any lease without a Payment row yet.
    total_outstanding_current = sum(
        (Decimal(p.outstanding_balance) for p in payments_this_month), Decimal("0")
    ) + sum(
        (expected_amount_for(db, l, current_year, current_month)
         for l in active_leases if l.id not in payment_by_lease),
        Decimal("0"),
    )
    total_outstanding_all = sum(
        (row.outstanding_total for row in rows if row.lease_id is not None),
        Decimal("0"),
    )

    stats = DashboardStats(
        properties_total=len(properties),
        active_leases=len(active_leases),
        current_month_paid=paid,
        current_month_partial=partial,
        current_month_unpaid=partial + unpaid_count,
        total_expected=total_expected,
        total_received=total_received,
        total_outstanding_current_month=total_outstanding_current,
        total_outstanding_all_months=total_outstanding_all,
        total_outstanding=total_outstanding_current,
    )

    return DashboardOut(stats=stats, rows=rows)

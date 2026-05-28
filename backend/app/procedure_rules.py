"""Computations around legal procedures (e.g. commandement de payer).

The procedure row stores the inputs (dates + decomposed amounts) and a
status column, but the canonical status is always recomputed from the
underlying payments. Keep this module free of HTTP / FastAPI imports so
both the procedures router and the dashboard router can reuse it.
"""

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from .models import Payment, Procedure, ProcedurePayment


def add_months(d: date, n: int) -> date:
    """Add `n` calendar months to `d` with last-day clamping
    (31 Jan + 1 mo -> 28/29 Feb)."""
    m_index = d.month - 1 + n
    y = d.year + m_index // 12
    m = m_index % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def default_deadline(procedure_type: str, notification_date: date) -> date:
    # Commandement de payer = 2 months by law (art. 24 loi du 6 juillet 1989).
    if procedure_type == "commandement_payer":
        return add_months(notification_date, 2)
    return notification_date


def attached_payments(
    db: Session, proc: Procedure,
) -> tuple[list[Payment], dict[int, str]]:
    """Return (payments, source_by_id). `source` is 'auto' (payment_date in
    [notification, deadline]) or 'manual' (explicit procedure_payments
    row). Auto wins when both apply."""
    auto = (
        db.query(Payment)
        .filter(
            Payment.lease_id == proc.lease_id,
            Payment.payment_date.isnot(None),
            Payment.payment_date >= proc.notification_date,
            Payment.payment_date <= proc.deadline_date,
        )
        .all()
    )
    auto_ids = {p.id for p in auto}
    manual_ids = {
        pid for (pid,) in
        db.query(ProcedurePayment.payment_id)
        .filter(ProcedurePayment.procedure_id == proc.id).all()
    }
    extras: list[Payment] = []
    if manual_ids - auto_ids:
        extras = (
            db.query(Payment)
            .filter(Payment.id.in_(manual_ids - auto_ids))
            .all()
        )
    source = {p.id: "auto" for p in auto}
    for p in extras:
        source[p.id] = "manual"
    all_payments = auto + extras
    all_payments.sort(
        key=lambda p: (p.payment_date is None, p.payment_date or date.min)
    )
    return all_payments, source


def compute_status_and_totals(
    proc: Procedure, payments: list[Payment],
) -> tuple[str, Decimal, Decimal, Decimal, int]:
    """Return (status, total_due, total_paid, remaining_due, days_remaining).

    - cancelled is sticky (manual).
    - paid iff total_paid >= total_due AND latest payment_date <= deadline.
    - expired_unpaid iff today > deadline (and not paid / cancelled).
    - else in_progress.
    """
    total_due = (
        Decimal(proc.amount_rent)
        + Decimal(proc.amount_fees)
        + Decimal(proc.amount_other)
    )
    total_paid = sum(
        (Decimal(p.received_amount) for p in payments), Decimal("0")
    )
    remaining = total_due - total_paid
    if remaining < 0:
        remaining = Decimal("0")
    today = date.today()
    days_remaining = (proc.deadline_date - today).days

    if proc.status == "cancelled":
        return "cancelled", total_due, total_paid, remaining, days_remaining

    if total_paid >= total_due and total_due > 0:
        dated = [p.payment_date for p in payments if p.payment_date is not None]
        last = max(dated) if dated else None
        if last is not None and last <= proc.deadline_date:
            return "paid", total_due, total_paid, remaining, days_remaining

    if today > proc.deadline_date:
        return "expired_unpaid", total_due, total_paid, remaining, days_remaining

    return "in_progress", total_due, total_paid, remaining, days_remaining

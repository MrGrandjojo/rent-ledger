"""Background scheduler — auto-generate monthly Payment records.

The job `create_monthly_payments` runs every day at 01:00 Europe/Paris.
On each run, and once at backend startup, it walks every active lease
and inserts a Payment row (status='unpaid', received_amount=0) for
every month between `lease.start_date` and today that does NOT already
have a payment. Each insert is recorded as an audit_log entry with
`user_display_name = "Système"` so it stands out in the Journaux tab.

Logging
-------
The job logs to the `app.scheduler` logger at INFO. To verify it ran:

    sudo podman logs rental-backend | grep "scheduler"

Expected on startup:
    INFO:app.scheduler:Scheduler started (job=create_monthly_payments, cron=01:00 Europe/Paris)
    INFO:app.scheduler:Startup catch-up — created N payment(s) across M lease(s)

Expected on the daily run:
    INFO:app.scheduler:create_monthly_payments triggered
    INFO:app.scheduler:create_monthly_payments — created N payment(s)
"""

from __future__ import annotations
import logging
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Iterable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from sqlalchemy.orm import Session

from .audit_log import log_event, snapshot_row
from .database import SessionLocal
from .lease_rules import expected_amount_for
from .models import Lease, Payment, Property, Tenant

logger = logging.getLogger("app.scheduler")

PARIS_TZ = pytz.timezone("Europe/Paris")

_PAYMENT_FIELDS = [
    "id", "lease_id", "year", "month", "expected_amount",
    "received_amount", "payment_date", "status", "outstanding_balance",
    "notes",
]

AUTO_NOTE = "Généré automatiquement"


def _payment_label(db: Session, lease: Lease, year: int, month: int) -> str:
    prop = db.get(Property, lease.property_id)
    tenant = db.get(Tenant, lease.tenant_id)
    parts = []
    if prop: parts.append(prop.name)
    if tenant: parts.append(f"{tenant.last_name} {tenant.first_name}".strip())
    parts.append(f"{month:02d}/{year}")
    return " / ".join(parts)


def _iter_months(start: date, end: date) -> Iterable[tuple[int, int]]:
    """Yield (year, month) pairs from `start`'s month inclusive to
    `end`'s month inclusive."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y += 1; m = 1
        else:
            m += 1


def _previous_month(d: date) -> tuple[int, int]:
    """Return (year, month) of the month immediately before `d`."""
    if d.month == 1:
        return d.year - 1, 12
    return d.year, d.month - 1


def _create_one(db: Session, lease: Lease, year: int, month: int) -> Payment | None:
    """Create an unpaid Payment row for (lease, year, month) if none
    exists. Returns the row (or None if it already existed). Logs an
    audit entry tagged with user_display_name='Système'."""
    existing = (
        db.query(Payment)
        .filter(Payment.lease_id == lease.id,
                Payment.year == year, Payment.month == month)
        .first()
    )
    if existing:
        return None
    expected = expected_amount_for(db, lease, year, month)
    payment = Payment(
        lease_id=lease.id,
        year=year, month=month,
        expected_amount=expected,
        received_amount=Decimal("0"),
        payment_date=None,
        notes=AUTO_NOTE,
        status="unpaid",
        outstanding_balance=expected,
    )
    db.add(payment)
    db.flush()
    after = snapshot_row(payment, _PAYMENT_FIELDS)
    after["origin"] = "scheduler"
    log_event(
        db, None,
        user_display_name="Système",
        action="create", entity_type="payment",
        entity_id=str(payment.id),
        entity_label=_payment_label(db, lease, year, month),
        after=after,
    )
    return payment


def run_catch_up(today: date | None = None) -> tuple[int, int]:
    """Create unpaid Payment records for every active lease for every
    month between `lease.start_date` and the **previous** calendar month
    (inclusive) that has no existing record. The CURRENT month is
    intentionally never auto-created — a month is only considered
    "missing/unpaid" once we have entered the following month and the
    user has not recorded a payment for it (per business rule v2.3).
    The current month, while in progress, may still be entered manually
    by the user — the scheduler simply does not force it.

    Returns (created_count, lease_count_touched). Safe to call
    repeatedly — already-existing payments are left alone and
    audit_log entries are only written for new rows.
    """
    today = today or date.today()
    cutoff_year, cutoff_month = _previous_month(today)
    if (cutoff_year, cutoff_month) < (1900, 1):
        # Sanity guard — nothing to catch up before the epoch
        return 0, 0
    cutoff = date(cutoff_year, cutoff_month, 1)
    db: Session = SessionLocal()
    created = 0
    touched: set[int] = set()
    try:
        leases = db.query(Lease).filter(Lease.is_active == True).all()  # noqa: E712
        for lease in leases:
            if lease.start_date is None or lease.start_date > cutoff:
                # Lease started in (or after) the current month — nothing
                # to catch up yet; the next month roll-over will pick it up.
                continue
            for (y, m) in _iter_months(lease.start_date, cutoff):
                p = _create_one(db, lease, y, m)
                if p is not None:
                    created += 1
                    touched.add(lease.id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("run_catch_up failed")
        raise
    finally:
        db.close()
    return created, len(touched)


def create_monthly_payments() -> None:
    """Scheduled job — runs every day at 01:00 Europe/Paris. Same logic
    as the startup catch-up: any missing month between each active
    lease's `start_date` and today gets an unpaid Payment row."""
    logger.info("create_monthly_payments triggered")
    try:
        created, touched = run_catch_up()
        logger.info(
            "create_monthly_payments — created %d payment(s) across %d lease(s)",
            created, touched,
        )
    except Exception:
        logger.exception("create_monthly_payments crashed")


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """Start the APScheduler instance. Called from main.py's lifespan
    after the DB is ready and the startup catch-up has run."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone=PARIS_TZ)
    sched.add_job(
        create_monthly_payments,
        trigger=CronTrigger(hour=1, minute=0, timezone=PARIS_TZ),
        id="create_monthly_payments",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "Scheduler started (job=create_monthly_payments, cron=01:00 Europe/Paris)"
    )
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")

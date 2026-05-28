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
import fcntl
import logging
import os
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Iterable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from sqlalchemy import text
from sqlalchemy.orm import Session

from .audit_log import log_event, snapshot_row
from .database import SessionLocal
from .lease_rules import expected_amount_for
from .models import Lease, Payment, Procedure, Property, Tenant
from .procedure_rules import attached_payments, compute_status_and_totals

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


def refresh_procedure_statuses() -> int:
    """Walk every Procedure and update the persisted `status` column from
    the recomputed value. The API always returns the recomputed status to
    clients (read-only on the request path), but the database column is
    kept in sync here so SQL-level reports / external integrations do not
    see stale values. Cancelled procedures are skipped (sticky state).

    Returns the number of rows whose status was updated.
    """
    db: Session = SessionLocal()
    updated = 0
    try:
        procs = db.query(Procedure).filter(Procedure.status != "cancelled").all()
        for proc in procs:
            payments, _ = attached_payments(db, proc)
            status_v, *_ = compute_status_and_totals(proc, payments)
            if proc.status != status_v:
                proc.status = status_v
                updated += 1
        if updated:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("refresh_procedure_statuses failed")
        raise
    finally:
        db.close()
    return updated


def _run_procedure_refresh() -> None:
    logger.info("refresh_procedure_statuses triggered")
    try:
        updated = refresh_procedure_statuses()
        logger.info("refresh_procedure_statuses — updated %d procedure(s)", updated)
    except Exception:
        logger.exception("refresh_procedure_statuses crashed")


def ensure_audit_partitions(years_ahead: int = 1) -> int:
    """Create missing yearly partitions of `audit_logs` for the current
    year + `years_ahead` years ahead. Called at boot and monthly so the
    next-year partition is always in place well before the year flips —
    a missing partition would make any `INSERT INTO audit_logs` fail.

    Returns the number of partitions created."""
    db: Session = SessionLocal()
    created = 0
    try:
        current_year = date.today().year
        for y in range(current_year, current_year + years_ahead + 1):
            part_name = f"audit_logs_{y}"
            row = db.execute(
                text("SELECT 1 FROM pg_class WHERE relname = :n"),
                {"n": part_name},
            ).fetchone()
            if row is None:
                db.execute(text(
                    f"CREATE TABLE {part_name} PARTITION OF audit_logs "
                    f"FOR VALUES FROM ('{y}-01-01') TO ('{y + 1}-01-01')"
                ))
                created += 1
        if created:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("ensure_audit_partitions failed")
        raise
    finally:
        db.close()
    return created


def _run_audit_partition_check() -> None:
    logger.info("ensure_audit_partitions triggered")
    try:
        created = ensure_audit_partitions()
        logger.info("ensure_audit_partitions — created %d partition(s)", created)
    except Exception:
        logger.exception("ensure_audit_partitions crashed")




_scheduler: BackgroundScheduler | None = None

# ── Worker election (multi-worker safety) ─────────────────────────────────────
# Uvicorn is started with --workers N (see Dockerfile). Each worker is a
# separate Python process and would otherwise spin up its own
# `BackgroundScheduler`, which would duplicate every job. We elect a single
# scheduler worker via an exclusive file lock that's held for the process'
# lifetime: only the first worker to acquire it runs the scheduler + the
# boot-time catch-up jobs. Other workers serve the API normally and skip
# all scheduler work.
#
# When the elected worker dies (crash, redeploy of one worker, OOM kill),
# the OS releases the lock and another worker picks it up on its next boot,
# so the system is self-healing.

SCHEDULER_LOCK_PATH = os.environ.get(
    "SCHEDULER_LOCK_PATH", "/tmp/rental-scheduler.lock"
)
_scheduler_lock_file = None  # keep open for the life of the process


def acquire_scheduler_lock() -> bool:
    """Return True if this worker should run the scheduler + boot jobs.

    The lock is process-scoped (`fcntl.flock`) so other workers in the
    same container coordinate without any external service. Other hosts
    would need a distributed lock (Redis, postgres advisory) — out of
    scope for the current single-host PME deployment.
    """
    global _scheduler_lock_file
    try:
        _scheduler_lock_file = open(SCHEDULER_LOCK_PATH, "w")
        fcntl.flock(_scheduler_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _scheduler_lock_file.write(f"pid={os.getpid()}\n")
        _scheduler_lock_file.flush()
        return True
    except BlockingIOError:
        # Another worker holds the lock — we're not the scheduler worker.
        if _scheduler_lock_file is not None:
            _scheduler_lock_file.close()
            _scheduler_lock_file = None
        return False
    except OSError as exc:
        logger.warning("Could not acquire scheduler lock (%s) — running as if elected", exc)
        return True


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
    sched.add_job(
        _run_procedure_refresh,
        trigger=CronTrigger(hour=1, minute=30, timezone=PARIS_TZ),
        id="refresh_procedure_statuses",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    # Audit log partition maintenance — monthly is enough since we always
    # provision (current_year + 1) at boot. Day-1 each month keeps the
    # buffer fresh and means the December → January roll-over is covered
    # well in advance.
    sched.add_job(
        _run_audit_partition_check,
        trigger=CronTrigger(day=1, hour=2, minute=0, timezone=PARIS_TZ),
        id="ensure_audit_partitions",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "Scheduler started (jobs=create_monthly_payments@01:00, "
        "refresh_procedure_statuses@01:30, "
        "ensure_audit_partitions@day-1 02:00 Europe/Paris)"
    )
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")

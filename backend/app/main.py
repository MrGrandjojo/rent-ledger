import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from .database import SessionLocal, engine, seed_initial_users
from .metrics import instrument_app
from .rate_limit import limiter
from .request_context import ClientIPMiddleware
from .routers import (
    admin, audit_logs, auth, charges, dashboard, documents, leases,
    payments, procedures, profile, properties, receipts, revisions, tenants,
)
from .scheduler import (
    acquire_scheduler_lock, ensure_audit_partitions,
    refresh_procedure_statuses, run_catch_up, shutdown_scheduler,
    start_scheduler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def wait_for_db(retries: int = 10, delay: float = 3.0):
    for attempt in range(retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection established")
            return
        except Exception as exc:
            logger.warning(f"DB not ready (attempt {attempt + 1}/{retries}): {exc}")
            time.sleep(delay)
    raise RuntimeError("Could not connect to the database after multiple retries")


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    # Schema is owned by db/init.sql (executed by Postgres on first boot of
    # the rental_db_data volume). The backend only seeds the bootstrap admin
    # and ensures every user has a profile row.
    db = SessionLocal()
    try:
        seed_initial_users(db)
    finally:
        db.close()

    # Worker election — with `--workers N`, only one process per container
    # runs the scheduler and the boot-time catch-ups (file lock on
    # /tmp/rental-scheduler.lock). Other workers serve the API only.
    is_scheduler_worker = acquire_scheduler_lock()
    if not is_scheduler_worker:
        logger.info(
            "Scheduler election: another worker holds the lock — this worker serves API only"
        )
    else:
        logger.info("Scheduler election: this worker runs the scheduler + boot jobs")

        # Startup catch-up — generate any missing monthly Payment rows so a
        # restart mid-month or after a downtime gap does not leave holes.
        try:
            created, touched = run_catch_up()
            logger.info(
                "Startup catch-up — created %d payment(s) across %d lease(s)",
                created, touched,
            )
        except Exception:
            logger.exception("Startup catch-up failed (continuing without it)")

        # Boot-time procedure status refresh — keeps the persisted `status`
        # column in sync with the recomputed value after any downtime gap.
        try:
            updated = refresh_procedure_statuses()
            logger.info("Startup CDP refresh — updated %d procedure(s)", updated)
        except Exception:
            logger.exception("Startup CDP refresh failed (continuing without it)")

        # Boot-time audit partition check — guarantees the current-year +
        # next-year partitions exist before any write hits audit_logs (a
        # missing partition would make INSERT fail with an obscure error).
        try:
            created = ensure_audit_partitions()
            logger.info("Startup audit partitions — created %d", created)
        except Exception:
            logger.exception("Startup audit partition check failed")

        start_scheduler()

    yield
    if is_scheduler_worker:
        shutdown_scheduler()


app = FastAPI(
    title="Rental API",
    root_path="/rental",
    lifespan=lifespan,
)

# Per-IP rate limiting (used by /api/auth/login). 429 responses are returned
# automatically by slowapi's handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# No CORS middleware — the SPA and API are served from the same origin via
# the nginx front. If you split the deployment, add CORSMiddleware here with
# an explicit allow_origins list (never "*" with credentials).

# Populate a ContextVar with the caller's IP so `audit_log.log_event` can
# record it on every CRUD action without each router having to thread a
# `Request` through. Reads the first hop of `X-Forwarded-For` when a reverse
# proxy sets it, otherwise the direct peer address.
app.add_middleware(ClientIPMiddleware)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(properties.router)
app.include_router(tenants.router)
app.include_router(leases.router)
app.include_router(revisions.router)
app.include_router(payments.router)
app.include_router(procedures.router)
app.include_router(charges.router)
app.include_router(documents.router)
app.include_router(receipts.router)
app.include_router(dashboard.router)
app.include_router(audit_logs.router)

# Prometheus instrumentation — exposes /api/metrics with HTTP request
# histograms + the business gauges defined in app/metrics.py. Must come
# after all routers are mounted so every endpoint is instrumented.
instrument_app(app)


@app.get("/api/health")
def health():
    return {"status": "ok"}

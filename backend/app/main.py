import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from .database import SessionLocal, engine, seed_initial_users
from .rate_limit import limiter
from .routers import (
    admin, audit_logs, auth, charges, dashboard, documents, leases,
    payments, profile, properties, receipts, revisions, tenants,
)
from .scheduler import run_catch_up, shutdown_scheduler, start_scheduler

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

    try:
        created, touched = run_catch_up()
        logger.info(
            "Startup catch-up — created %d payment(s) across %d lease(s)",
            created, touched,
        )
    except Exception:
        logger.exception("Startup catch-up failed (continuing without it)")

    start_scheduler()

    yield
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

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(properties.router)
app.include_router(tenants.router)
app.include_router(leases.router)
app.include_router(revisions.router)
app.include_router(payments.router)
app.include_router(charges.router)
app.include_router(documents.router)
app.include_router(receipts.router)
app.include_router(dashboard.router)
app.include_router(audit_logs.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

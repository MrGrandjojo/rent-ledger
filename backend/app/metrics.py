"""Prometheus metrics exposed at /api/metrics.

Two layers:

- HTTP request metrics (latency histogram, request count, in-progress,
  status code) installed by `prometheus-fastapi-instrumentator` via
  `instrument_app(app)`. These are **per-worker** (each uvicorn worker
  has its own registry) — a single scrape sees one worker's view of
  traffic. Grafana smooths it out over time; acceptable for the typical
  single-host deployment with a handful of users.
- Business gauges (active leases, CDP counts, etc.) refreshed
  **on every scrape** on the responding worker so the value is always
  fresh regardless of which worker Prometheus lands on. Cost is 7 simple
  `SELECT COUNT(*)` per scrape — negligible at 15s scrape interval.

Scrape config (Prometheus / Grafana Agent):

    scrape_configs:
      - job_name: rental
        scrape_interval: 15s
        metrics_path: /api/metrics
        static_configs:
          - targets: ['rental-host:8080']

Metrics are **unauthenticated** by design — the endpoint is meant to be
reached from an internal monitoring network. Block external scrapes at
the reverse proxy / firewall if the host is internet-facing.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from .database import SessionLocal

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("app.metrics")


# ── Business gauges (refreshed by the scheduler) ─────────────────────────────

LEASES_ACTIVE = Gauge(
    "rental_active_leases",
    "Number of active leases (is_active=true).",
)
PROPERTIES_TOTAL = Gauge(
    "rental_properties_total",
    "Number of properties registered.",
)
TENANTS_TOTAL = Gauge(
    "rental_tenants_total",
    "Number of tenants registered.",
)
CDP_IN_PROGRESS = Gauge(
    "rental_cdp_in_progress",
    "Number of procedures (commandement de payer) with status='in_progress'.",
)
CDP_EXPIRED_UNPAID = Gauge(
    "rental_cdp_expired_unpaid",
    "Number of CDP procedures past their deadline without règlement.",
)
PAYMENTS_UNPAID_CURRENT = Gauge(
    "rental_payments_unpaid_current_month",
    "Number of unpaid Payment rows for the current calendar month.",
)
AUDIT_LOGS_TOTAL = Gauge(
    "rental_audit_logs_total",
    "Total rows in audit_logs (all partitions).",
)


def refresh_business_gauges() -> None:
    """Single SQL query per metric — cheap even at a few thousand leases.
    Called from the /api/metrics handler so the value is always fresh on
    the responding worker."""
    db = SessionLocal()
    try:
        LEASES_ACTIVE.set(
            db.execute(text("SELECT COUNT(*) FROM leases WHERE is_active")).scalar() or 0
        )
        PROPERTIES_TOTAL.set(
            db.execute(text("SELECT COUNT(*) FROM properties")).scalar() or 0
        )
        TENANTS_TOTAL.set(
            db.execute(text("SELECT COUNT(*) FROM tenants")).scalar() or 0
        )
        CDP_IN_PROGRESS.set(
            db.execute(text(
                "SELECT COUNT(*) FROM procedures WHERE status = 'in_progress'"
            )).scalar() or 0
        )
        CDP_EXPIRED_UNPAID.set(
            db.execute(text(
                "SELECT COUNT(*) FROM procedures WHERE status = 'expired_unpaid'"
            )).scalar() or 0
        )
        PAYMENTS_UNPAID_CURRENT.set(
            db.execute(text(
                "SELECT COUNT(*) FROM payments "
                "WHERE status = 'unpaid' "
                "AND year = EXTRACT(YEAR FROM NOW())::INT "
                "AND month = EXTRACT(MONTH FROM NOW())::INT"
            )).scalar() or 0
        )
        AUDIT_LOGS_TOTAL.set(
            db.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar() or 0
        )
    finally:
        db.close()


# ── HTTP instrumentation (latency histogram, request count, etc.) ────────────

def instrument_app(app: "FastAPI") -> None:
    """Attach the FastAPI HTTP instrumentator (middleware) and register
    a custom /api/metrics handler that refreshes the business gauges on
    every scrape — see the module docstring for the multi-worker rationale.

    Idempotent: safe to call from main.py at every worker boot."""
    Instrumentator(
        # Keep /metrics out of the histogram (scrapes would dominate stats).
        excluded_handlers=["/api/metrics"],
        # Skip 404s on unknown paths — noise from spurious clients.
        should_ignore_untemplated=True,
    ).instrument(app)
    # Do NOT call .expose() — we register our own handler so we can refresh
    # the business gauges before serialising.

    @app.get("/api/metrics", include_in_schema=False, tags=["monitoring"])
    async def metrics_endpoint() -> Response:
        # Refresh on the responding worker so the gauge values are always
        # up-to-date regardless of which worker the scraper hit.
        try:
            refresh_business_gauges()
        except Exception:
            logger.exception("metrics refresh failed at scrape time")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

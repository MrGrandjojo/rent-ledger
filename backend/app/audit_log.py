"""Append-only audit-log helper.

All event recording in routers goes through `log_event`. The helper writes
to `audit_logs` and commits — `audit_logs` must never be updated or
deleted from application code except through the dedicated admin-only
purge endpoint.

Snapshots stored on the row (`user_display_name`, `entity_label`) keep
the log human-readable after the underlying entity is removed.
"""

from __future__ import annotations
from typing import Any, Optional
from sqlalchemy.orm import Session

from .models import AuditLog, User


ALLOWED_ACTIONS = (
    "create", "update", "delete", "export", "login", "login_failed",
)
ALLOWED_ENTITY_TYPES = (
    "property", "lease", "tenant", "payment", "rent_revision",
    "charge_regularization", "document", "user", "group", "audit_log",
    "auth",
)


def _user_display_name(user: Optional[User]) -> str:
    if user is None:
        return "system"
    profile = getattr(user, "profile", None)
    if profile and profile.landlord_name:
        return f"{user.username} ({profile.landlord_name})"
    return user.username


def log_event(
    db: Session,
    user: Optional[User],
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    entity_label: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_display_name: Optional[str] = None,
) -> AuditLog:
    """Insert an audit_log row and commit.

    `user=None` is used for system-triggered events (scheduled jobs,
    startup catch-up, etc.). `user_display_name` may be passed explicitly
    to override the default — e.g. the background scheduler passes
    `"Système"` so its rows are immediately readable in the Journaux tab.
    `before` / `after` are stored as JSONB; pass plain dicts of primitives
    only.
    """
    entry = AuditLog(
        user_id=user.id if user else None,
        user_display_name=user_display_name or _user_display_name(user),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        entity_label=entity_label,
        before=before,
        after=after,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def jsonify(value: Any) -> Any:
    """Convert a value to a JSONB-safe representation: Decimal → str,
    date/datetime → ISO string, None passes through."""
    from datetime import date as _date, datetime as _datetime
    from decimal import Decimal as _Decimal
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, _Decimal):
        return str(value)
    if isinstance(value, (_date, _datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonify(v) for v in value]
    return str(value)


def snapshot_row(obj: Any, fields: list[str]) -> dict:
    """Serialise the named attributes of an ORM object to a JSON-safe dict."""
    if obj is None:
        return {}
    return {f: jsonify(getattr(obj, f, None)) for f in fields}

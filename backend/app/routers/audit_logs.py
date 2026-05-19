"""Audit log endpoints — admin-only.

`require_admin` is the strict gate here: supervisors are deliberately
excluded from listing, exporting, and deleting logs.
"""

import csv
import io
import json
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..audit_log import log_event
from ..database import get_db
from ..dependencies import get_current_user, require_admin
from ..models import AuditLog, User
from ..schemas import AuditLogOut

router = APIRouter(
    prefix="/api/audit-logs",
    tags=["audit-logs"],
    dependencies=[Depends(require_admin)],
)


def _apply_filters(q, start: Optional[datetime], end: Optional[datetime],
                   user_id: Optional[int], entity_type: Optional[str],
                   action: Optional[str]):
    if start is not None:
        q = q.filter(AuditLog.created_at >= start)
    if end is not None:
        q = q.filter(AuditLog.created_at <= end)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(AuditLog.action == action)
    return q


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    db: Session = Depends(get_db),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    entity_type: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=500, le=2000),
):
    q = db.query(AuditLog)
    q = _apply_filters(q, start, end, user_id, entity_type, action)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/export")
def export_audit_logs_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    entity_type: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
):
    q = db.query(AuditLog)
    q = _apply_filters(q, start, end, user_id, entity_type, action)
    rows = q.order_by(AuditLog.created_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "id", "created_at", "user_id", "user", "action", "entity_type",
        "entity_id", "entity_label", "before", "after", "ip_address",
    ])
    for r in rows:
        writer.writerow([
            r.id,
            r.created_at.astimezone().isoformat() if r.created_at else "",
            r.user_id or "",
            r.user_display_name or "",
            r.action,
            r.entity_type,
            r.entity_id or "",
            r.entity_label or "",
            json.dumps(r.before, ensure_ascii=False) if r.before else "",
            json.dumps(r.after, ensure_ascii=False) if r.after else "",
            r.ip_address or "",
        ])

    # The export itself is an auditable event.
    log_event(
        db, current_user, action="export", entity_type="audit_log",
        entity_label="CSV export",
        after={"row_count": len(rows)},
    )

    buf.seek(0)
    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("", status_code=200)
def delete_all_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Purge every audit_log row. The deletion action itself is recorded
    AFTER the purge so the trail of the purge survives."""
    count = db.query(AuditLog).delete()
    db.commit()
    log_event(
        db, current_user, action="delete", entity_type="audit_log",
        entity_label="Purge totale des journaux",
        before={"rows_deleted": count},
    )
    return {"deleted": count}

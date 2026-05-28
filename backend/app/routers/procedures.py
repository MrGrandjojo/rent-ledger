"""Legal procedures against a tenant — initially "commandement de payer".

The status (`in_progress` / `paid` / `expired_unpaid` / `cancelled`) is recomputed
on every read from the underlying payments + dates. The row's `status` column
is updated when the read computes a different value, so it stays correct for
dashboards and external SQL too, but the canonical truth always lives in the
payments table.

Imputation of payments to a procedure has two sources:

- **Auto** — every Payment of the same lease whose `payment_date` falls inside
  `[notification_date, deadline_date]`. Computed on the fly, never stored.
- **Manual** — extra payments explicitly attached via the `procedure_payments`
  table. Covers the case where the tenant pays *between* the day the landlord
  requests the act and the day the bailiff actually serves it: that payment
  belongs to the procedure even though it's dated before `notification_date`.

Visibility: a procedure is accessible iff its lease is accessible (regular
users get scoping via groups; admins/supervisors see everything).
Creation/edition/deletion: any user with lease access (no admin gate).
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit_log import log_event, snapshot_row
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_lease_access, get_current_user,
    has_global_access, require_admin_or_supervisor,
)
from ..models import Lease, Payment, Procedure, ProcedurePayment, Property, Tenant, User
from ..procedure_rules import (
    attached_payments, compute_status_and_totals, default_deadline,
)
from ..schemas import (
    ProcedureAttachedPayment, ProcedureCreate, ProcedureDetailOut,
    ProcedureOut, ProcedurePaymentAttach, ProcedureUpdate,
)

router = APIRouter(prefix="/api/procedures", tags=["procedures"])

_PROC_FIELDS = [
    "id", "lease_id", "parent_procedure_id", "procedure_type",
    "notification_date", "deadline_date",
    "amount_rent", "amount_fees", "amount_other",
    "status", "bailiff_name", "act_reference", "notes",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _proc_label(db: Session, proc: Procedure) -> str:
    lease = db.get(Lease, proc.lease_id)
    if lease is None:
        return f"Procédure #{proc.id}"
    prop = db.get(Property, lease.property_id)
    tenant = db.get(Tenant, lease.tenant_id)
    parts = ["CDP"]
    if prop: parts.append(prop.name)
    if tenant: parts.append(f"{tenant.last_name} {tenant.first_name}".strip())
    parts.append(proc.notification_date.strftime("%d/%m/%Y"))
    return " / ".join(parts)


def _proc_visible(db: Session, user: User, proc: Procedure) -> bool:
    if has_global_access(user):
        return True
    ids = accessible_property_ids(db, user) or set()
    lease = db.get(Lease, proc.lease_id)
    return bool(lease and lease.property_id in ids)


def _build_out(proc: Procedure, payments, source, *, detail: bool = False):
    """Pure-Python view model — never touches the DB. The persisted
    `proc.status` may be stale; the recomputed `status_v` is what we
    return to clients. The column itself is converged by the
    `refresh_procedure_statuses` scheduler job (daily at 01:30 + boot
    catch-up), not on the request path."""
    status_v, total_due, total_paid, remaining, days_remaining = \
        compute_status_and_totals(proc, payments)
    base = {
        "id": proc.id,
        "lease_id": proc.lease_id,
        "parent_procedure_id": proc.parent_procedure_id,
        "procedure_type": proc.procedure_type,
        "notification_date": proc.notification_date,
        "deadline_date": proc.deadline_date,
        "amount_rent": Decimal(proc.amount_rent),
        "amount_fees": Decimal(proc.amount_fees),
        "amount_other": Decimal(proc.amount_other),
        "status": status_v,
        "bailiff_name": proc.bailiff_name,
        "act_reference": proc.act_reference,
        "notes": proc.notes,
        "created_at": proc.created_at,
        "updated_at": proc.updated_at,
        "total_due": total_due,
        "total_paid": total_paid,
        "remaining_due": remaining,
        "days_remaining": days_remaining,
        "attached_payments_count": len(payments),
    }
    if not detail:
        return ProcedureOut(**base)
    return ProcedureDetailOut(
        **base,
        attached_payments=[
            ProcedureAttachedPayment(payment=p, source=source[p.id])
            for p in payments
        ],
    )


def _to_out(db: Session, proc: Procedure, *, detail: bool = False):
    """Single-procedure adapter — used by GET /{id}, POST, PUT, cancel,
    attach/detach. Issues 2 queries (manual links + auto-window payments)."""
    payments, source = attached_payments(db, proc)
    return _build_out(proc, payments, source, detail=detail)


def _batch_to_out(db: Session, procs: list[Procedure]) -> list[ProcedureOut]:
    """Batched version of `_to_out` for the list endpoint — avoids the
    N+1 query pattern by loading all manual links and lease payments in
    two queries total, then dispatching in memory."""
    if not procs:
        return []
    proc_ids = [p.id for p in procs]
    lease_ids = list({p.lease_id for p in procs})

    manual_links = (
        db.query(ProcedurePayment.procedure_id, ProcedurePayment.payment_id)
        .filter(ProcedurePayment.procedure_id.in_(proc_ids))
        .all()
    )
    manual_by_proc: dict[int, set[int]] = {}
    for proc_id, pay_id in manual_links:
        manual_by_proc.setdefault(proc_id, set()).add(pay_id)

    payments = (
        db.query(Payment)
        .filter(Payment.lease_id.in_(lease_ids))
        .all()
    )
    payments_by_id = {p.id: p for p in payments}
    payments_by_lease: dict[int, list[Payment]] = {}
    for p in payments:
        payments_by_lease.setdefault(p.lease_id, []).append(p)

    out: list[ProcedureOut] = []
    for proc in procs:
        auto = [
            p for p in payments_by_lease.get(proc.lease_id, [])
            if p.payment_date is not None
            and proc.notification_date <= p.payment_date <= proc.deadline_date
        ]
        auto_ids = {p.id for p in auto}
        extra_ids = manual_by_proc.get(proc.id, set()) - auto_ids
        extras = [payments_by_id[pid] for pid in extra_ids if pid in payments_by_id]

        all_payments = auto + extras
        all_payments.sort(
            key=lambda p: (p.payment_date is None, p.payment_date or date.min)
        )
        source = {p.id: "auto" for p in auto}
        for p in extras:
            source[p.id] = "manual"
        out.append(_build_out(proc, all_payments, source))
    return out


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProcedureOut])
def list_procedures(
    lease_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Procedure)
    if lease_id is not None:
        assert_lease_access(db, user, lease_id)
        q = q.filter(Procedure.lease_id == lease_id)
    else:
        ids = accessible_property_ids(db, user)
        if ids is not None:
            if not ids:
                return []
            q = q.join(Lease, Lease.id == Procedure.lease_id).filter(
                Lease.property_id.in_(ids)
            )
    procs = q.order_by(Procedure.notification_date.desc(), Procedure.id.desc()).all()
    out = _batch_to_out(db, procs)
    if status:
        out = [p for p in out if p.status == status]
    return out


@router.post("", response_model=ProcedureOut, status_code=201)
def create_procedure(
    body: ProcedureCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_lease_access(db, user, body.lease_id)
    if body.parent_procedure_id is not None:
        parent = db.get(Procedure, body.parent_procedure_id)
        if not parent or not _proc_visible(db, user, parent):
            raise HTTPException(404, "Procédure parente introuvable")
        if parent.lease_id != body.lease_id:
            raise HTTPException(400, "La procédure parente n'appartient pas au même bail")

    deadline = body.deadline_date or default_deadline(body.procedure_type, body.notification_date)
    if deadline < body.notification_date:
        raise HTTPException(400, "L'échéance ne peut pas précéder la date de notification")

    proc = Procedure(
        lease_id=body.lease_id,
        parent_procedure_id=body.parent_procedure_id,
        procedure_type=body.procedure_type,
        notification_date=body.notification_date,
        deadline_date=deadline,
        amount_rent=body.amount_rent,
        amount_fees=body.amount_fees,
        amount_other=body.amount_other,
        bailiff_name=(body.bailiff_name or None),
        act_reference=(body.act_reference or None),
        notes=(body.notes or None),
        status="in_progress",
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)
    log_event(
        db, user, action="create", entity_type="procedure",
        entity_id=str(proc.id), entity_label=_proc_label(db, proc),
        after=snapshot_row(proc, _PROC_FIELDS),
    )
    return _to_out(db, proc)


@router.get("/{procedure_id}", response_model=ProcedureDetailOut)
def get_procedure(
    procedure_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proc = db.get(Procedure, procedure_id)
    if not proc or not _proc_visible(db, user, proc):
        raise HTTPException(404, "Procédure introuvable")
    return _to_out(db, proc, detail=True)


@router.put("/{procedure_id}", response_model=ProcedureOut)
def update_procedure(
    procedure_id: int,
    body: ProcedureUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proc = db.get(Procedure, procedure_id)
    if not proc or not _proc_visible(db, user, proc):
        raise HTTPException(404, "Procédure introuvable")
    before = snapshot_row(proc, _PROC_FIELDS)

    if body.notification_date is not None:
        proc.notification_date = body.notification_date
    if body.deadline_date is not None:
        proc.deadline_date = body.deadline_date
    if body.amount_rent is not None:
        proc.amount_rent = body.amount_rent
    if body.amount_fees is not None:
        proc.amount_fees = body.amount_fees
    if body.amount_other is not None:
        proc.amount_other = body.amount_other
    if body.bailiff_name is not None:
        proc.bailiff_name = body.bailiff_name or None
    if body.act_reference is not None:
        proc.act_reference = body.act_reference or None
    if body.notes is not None:
        proc.notes = body.notes or None

    if proc.deadline_date < proc.notification_date:
        raise HTTPException(400, "L'échéance ne peut pas précéder la date de notification")

    db.commit()
    db.refresh(proc)
    log_event(
        db, user, action="update", entity_type="procedure",
        entity_id=str(proc.id), entity_label=_proc_label(db, proc),
        before=before, after=snapshot_row(proc, _PROC_FIELDS),
    )
    return _to_out(db, proc)


@router.delete("/{procedure_id}", status_code=204)
def delete_procedure(
    procedure_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_supervisor),
):
    """Suppression réservée à admin/supervisor — action irréversible sur
    une donnée juridique. Création / édition / annulation restent
    ouvertes à tout utilisateur ayant accès au bail."""
    proc = db.get(Procedure, procedure_id)
    if not proc or not _proc_visible(db, user, proc):
        raise HTTPException(404, "Procédure introuvable")
    before = snapshot_row(proc, _PROC_FIELDS)
    label = _proc_label(db, proc)
    db.delete(proc)
    db.commit()
    log_event(
        db, user, action="delete", entity_type="procedure",
        entity_id=str(procedure_id), entity_label=label, before=before,
    )


@router.post("/{procedure_id}/cancel", response_model=ProcedureOut)
def cancel_procedure(
    procedure_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proc = db.get(Procedure, procedure_id)
    if not proc or not _proc_visible(db, user, proc):
        raise HTTPException(404, "Procédure introuvable")
    if proc.status == "cancelled":
        return _to_out(db, proc)
    before = snapshot_row(proc, _PROC_FIELDS)
    proc.status = "cancelled"
    db.commit()
    db.refresh(proc)
    log_event(
        db, user, action="update", entity_type="procedure",
        entity_id=str(proc.id), entity_label=_proc_label(db, proc),
        before=before, after=snapshot_row(proc, _PROC_FIELDS),
    )
    return _to_out(db, proc)


@router.post("/{procedure_id}/payments", response_model=ProcedureDetailOut, status_code=201)
def attach_payment(
    procedure_id: int,
    body: ProcedurePaymentAttach,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proc = db.get(Procedure, procedure_id)
    if not proc or not _proc_visible(db, user, proc):
        raise HTTPException(404, "Procédure introuvable")
    payment = db.get(Payment, body.payment_id)
    if not payment or payment.lease_id != proc.lease_id:
        raise HTTPException(404, "Paiement introuvable pour ce bail")
    existing = db.get(ProcedurePayment, (procedure_id, body.payment_id))
    if existing is None:
        db.add(ProcedurePayment(procedure_id=procedure_id, payment_id=body.payment_id))
        db.commit()
        log_event(
            db, user, action="update", entity_type="procedure",
            entity_id=str(proc.id), entity_label=_proc_label(db, proc),
            after={"attached_payment_id": body.payment_id},
        )
    return _to_out(db, proc, detail=True)


@router.delete("/{procedure_id}/payments/{payment_id}", response_model=ProcedureDetailOut)
def detach_payment(
    procedure_id: int,
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proc = db.get(Procedure, procedure_id)
    if not proc or not _proc_visible(db, user, proc):
        raise HTTPException(404, "Procédure introuvable")
    link = db.get(ProcedurePayment, (procedure_id, payment_id))
    if link is not None:
        db.delete(link)
        db.commit()
        log_event(
            db, user, action="update", entity_type="procedure",
            entity_id=str(proc.id), entity_label=_proc_label(db, proc),
            before={"detached_payment_id": payment_id},
        )
    return _to_out(db, proc, detail=True)

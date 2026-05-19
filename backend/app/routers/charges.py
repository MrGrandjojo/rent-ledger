from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_lease_access, get_current_user,
    has_global_access,
)
from ..models import ChargesRegularization, Lease, User
from ..schemas import ChargesCreate, ChargesOut, ChargesUpdate

router = APIRouter(prefix="/api/charges", tags=["charges"])


def _reg_visible(db: Session, user: User, reg: ChargesRegularization) -> bool:
    if has_global_access(user):
        return True
    ids = accessible_property_ids(db, user) or set()
    lease = db.get(Lease, reg.lease_id)
    return bool(lease and lease.property_id in ids)


@router.get("", response_model=list[ChargesOut])
def list_charges(lease_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(ChargesRegularization)
    if lease_id is not None:
        assert_lease_access(db, user, lease_id)
        q = q.filter(ChargesRegularization.lease_id == lease_id)
    else:
        ids = accessible_property_ids(db, user)
        if ids is not None:
            if not ids:
                return []
            q = q.join(Lease, Lease.id == ChargesRegularization.lease_id).filter(Lease.property_id.in_(ids))
    return q.order_by(ChargesRegularization.year.desc()).all()


@router.post("", response_model=ChargesOut, status_code=201)
def create_charges(body: ChargesCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_lease_access(db, user, body.lease_id)
    existing = db.query(ChargesRegularization).filter_by(
        lease_id=body.lease_id, year=body.year
    ).first()
    if existing:
        raise HTTPException(409, "Une régularisation existe déjà pour cette année")
    balance = body.total_actual_charges - body.total_provisions_collected
    reg = ChargesRegularization(
        **body.model_dump(),
        balance=balance,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg


@router.get("/{reg_id}", response_model=ChargesOut)
def get_charges(reg_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    reg = db.get(ChargesRegularization, reg_id)
    if not reg or not _reg_visible(db, user, reg):
        raise HTTPException(404, "Régularisation introuvable")
    return reg


@router.put("/{reg_id}", response_model=ChargesOut)
def update_charges(reg_id: int, body: ChargesUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    reg = db.get(ChargesRegularization, reg_id)
    if not reg or not _reg_visible(db, user, reg):
        raise HTTPException(404, "Régularisation introuvable")
    reg.total_actual_charges = body.total_actual_charges
    reg.total_provisions_collected = body.total_provisions_collected
    reg.balance = body.total_actual_charges - body.total_provisions_collected
    reg.notes = body.notes
    db.commit()
    db.refresh(reg)
    return reg


@router.delete("/{reg_id}", status_code=204)
def delete_charges(reg_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    reg = db.get(ChargesRegularization, reg_id)
    if not reg or not _reg_visible(db, user, reg):
        raise HTTPException(404, "Régularisation introuvable")
    db.delete(reg)
    db.commit()

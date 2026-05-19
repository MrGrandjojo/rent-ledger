from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..audit_log import log_event, snapshot_row
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_property_access,
    get_current_user, require_admin_or_supervisor,
)
from ..models import Property, User
from ..schemas import PropertyCreate, PropertyOut, PropertyUpdate

router = APIRouter(prefix="/api/properties", tags=["properties"])

_PROPERTY_FIELDS = [
    "id", "name", "type", "address_street", "address_city",
    "address_zip", "address_country",
]


@router.get("", response_model=list[PropertyOut])
def list_properties(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Property)
    ids = accessible_property_ids(db, user)
    if ids is not None:
        if not ids:
            return []
        q = q.filter(Property.id.in_(ids))
    return q.order_by(Property.name).all()


@router.post("", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_supervisor)):
    prop = Property(**body.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    log_event(
        db, current_user, action="create", entity_type="property",
        entity_id=str(prop.id), entity_label=prop.name,
        after=snapshot_row(prop, _PROPERTY_FIELDS),
    )
    return prop


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return assert_property_access(db, user, property_id)


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, body: PropertyUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_supervisor)):
    prop = assert_property_access(db, current_user, property_id)
    before = snapshot_row(prop, _PROPERTY_FIELDS)
    for k, v in body.model_dump().items():
        setattr(prop, k, v)
    db.commit()
    db.refresh(prop)
    after = snapshot_row(prop, _PROPERTY_FIELDS)
    diff_before = {k: v for k, v in before.items() if before.get(k) != after.get(k)}
    if diff_before:
        log_event(
            db, current_user, action="update", entity_type="property",
            entity_id=str(prop.id), entity_label=prop.name,
            before=diff_before,
            after={k: after.get(k) for k in diff_before},
        )
    return prop


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_supervisor)):
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(404, "Bien introuvable")
    before = snapshot_row(prop, _PROPERTY_FIELDS)
    label = prop.name
    db.delete(prop)
    db.commit()
    log_event(
        db, current_user, action="delete", entity_type="property",
        entity_id=str(property_id), entity_label=label, before=before,
    )

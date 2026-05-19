"""Management endpoints: user management + group management.

Every route is gated by `require_admin_or_supervisor` — admins and
supervisors have full access to user and group management. The single
restriction is that a supervisor cannot promote a user to (or create) the
admin role; that is enforced inside the relevant handlers below.

Audit-log endpoints live in a separate router (`audit_logs`) gated by the
strict `require_admin` so supervisors cannot touch logs.
"""

import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit_log import log_event
from ..auth import hash_password
from ..database import get_db
from ..dependencies import (
    get_current_user, require_admin_or_supervisor,
)
from ..models import (
    Group, Property, User, UserProfile,
    group_properties, user_groups,
)
from ..schemas import (
    AdminUserCreate, AdminUserOut, AdminUserUpdate,
    GroupCreate, GroupDetailOut, GroupMembersUpdate,
    GroupOut, GroupPropertiesUpdate, GroupUpdate, TempPasswordOut,
)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_or_supervisor)])


def _generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active == True).count()  # noqa: E712


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("/users", response_model=AdminUserOut, status_code=201)
def create_user(
    body: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.role == "admin" and current_user.role != "admin":
        raise HTTPException(403, "Seul un administrateur peut créer un compte administrateur")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "Nom d'utilisateur déjà utilisé")
    user = User(
        username=body.username,
        email=body.email,
        role=body.role,
        is_active=True,
        password_hash=hash_password(body.temporary_password),
        force_password_change=True,
    )
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    db.commit()
    db.refresh(user)
    log_event(
        db, current_user, action="create", entity_type="user",
        entity_id=str(user.id),
        entity_label=user.username,
        after={"username": user.username, "role": user.role},
    )
    return user


@router.put("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    # Supervisors cannot promote anyone to admin.
    if body.role == "admin" and current_user.role != "admin":
        raise HTTPException(403, "Seul un administrateur peut promouvoir un utilisateur en administrateur")
    # Supervisors cannot demote/edit an existing admin (would let them strip
    # the last admin via deactivation as well).
    if user.role == "admin" and current_user.role != "admin" and (
        body.role is not None and body.role != "admin"
        or body.is_active is False
    ):
        raise HTTPException(403, "Un superviseur ne peut pas modifier un administrateur")

    # Forbid demoting / deactivating the last active admin.
    would_remove_admin = (
        (body.role is not None and body.role != "admin" and user.role == "admin")
        or (body.is_active is False and user.role == "admin" and user.is_active)
    )
    if would_remove_admin and _admin_count(db) <= 1:
        raise HTTPException(400, "Au moins un administrateur actif doit subsister")

    old_role = user.role
    old_active = user.is_active

    if body.email is not None:
        user.email = body.email
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)

    if body.role is not None and body.role != old_role:
        log_event(
            db, current_user, action="update", entity_type="user",
            entity_id=str(user.id), entity_label=user.username,
            before={"role": old_role}, after={"role": user.role},
        )
    if body.is_active is not None and body.is_active != old_active:
        log_event(
            db, current_user, action="update", entity_type="user",
            entity_id=str(user.id), entity_label=user.username,
            before={"active": old_active}, after={"active": user.is_active},
        )
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    if user.id == current_user.id:
        raise HTTPException(400, "Vous ne pouvez pas supprimer votre propre compte")
    if user.role == "admin" and current_user.role != "admin":
        raise HTTPException(403, "Un superviseur ne peut pas supprimer un administrateur")
    if user.role == "admin" and _admin_count(db) <= 1:
        raise HTTPException(400, "Au moins un administrateur actif doit subsister")
    snapshot = {"username": user.username, "role": user.role}
    label = user.username
    db.delete(user)
    db.commit()
    log_event(
        db, current_user, action="delete", entity_type="user",
        entity_id=str(user_id), entity_label=label, before=snapshot,
    )


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordOut)
def reset_user_password(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")
    temp = _generate_temp_password()
    user.password_hash = hash_password(temp)
    user.force_password_change = True
    db.commit()
    return TempPasswordOut(temporary_password=temp)


# ── Groups ────────────────────────────────────────────────────────────────────

def _group_to_summary(db: Session, group: Group) -> GroupOut:
    member_count = db.query(user_groups).filter(user_groups.c.group_id == group.id).count()
    property_count = db.query(group_properties).filter(group_properties.c.group_id == group.id).count()
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        member_count=member_count,
        property_count=property_count,
        created_at=group.created_at,
    )


@router.get("/groups", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    groups = db.query(Group).order_by(Group.name).all()
    return [_group_to_summary(db, g) for g in groups]


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(body: GroupCreate, db: Session = Depends(get_db)):
    if db.query(Group).filter(Group.name == body.name).first():
        raise HTTPException(409, "Un groupe avec ce nom existe déjà")
    group = Group(name=body.name, description=body.description)
    db.add(group)
    db.commit()
    db.refresh(group)
    return _group_to_summary(db, group)


@router.get("/groups/{group_id}", response_model=GroupDetailOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Groupe introuvable")
    user_ids = [row[0] for row in db.query(user_groups.c.user_id)
                .filter(user_groups.c.group_id == group_id).all()]
    property_ids = [row[0] for row in db.query(group_properties.c.property_id)
                    .filter(group_properties.c.group_id == group_id).all()]
    return GroupDetailOut(
        id=group.id,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        user_ids=user_ids,
        property_ids=property_ids,
    )


@router.put("/groups/{group_id}", response_model=GroupOut)
def update_group(group_id: int, body: GroupUpdate, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Groupe introuvable")
    if body.name is not None and body.name != group.name:
        if db.query(Group).filter(Group.name == body.name).first():
            raise HTTPException(409, "Un groupe avec ce nom existe déjà")
        group.name = body.name
    if body.description is not None:
        group.description = body.description
    db.commit()
    db.refresh(group)
    return _group_to_summary(db, group)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Groupe introuvable")
    db.delete(group)
    db.commit()


@router.put("/groups/{group_id}/users", response_model=GroupDetailOut)
def set_group_members(group_id: int, body: GroupMembersUpdate, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Groupe introuvable")
    # Validate every supplied user_id exists.
    if body.user_ids:
        existing = {row[0] for row in db.query(User.id).filter(User.id.in_(body.user_ids)).all()}
        missing = set(body.user_ids) - existing
        if missing:
            raise HTTPException(400, f"Utilisateur(s) introuvable(s) : {sorted(missing)}")
    db.execute(user_groups.delete().where(user_groups.c.group_id == group_id))
    for uid in set(body.user_ids):
        db.execute(user_groups.insert().values(user_id=uid, group_id=group_id))
    db.commit()
    return get_group(group_id, db)


@router.put("/groups/{group_id}/properties", response_model=GroupDetailOut)
def set_group_properties(group_id: int, body: GroupPropertiesUpdate, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Groupe introuvable")
    if body.property_ids:
        existing = {row[0] for row in db.query(Property.id).filter(Property.id.in_(body.property_ids)).all()}
        missing = set(body.property_ids) - existing
        if missing:
            raise HTTPException(400, f"Bien(s) introuvable(s) : {sorted(missing)}")
    db.execute(group_properties.delete().where(group_properties.c.group_id == group_id))
    for pid in set(body.property_ids):
        db.execute(group_properties.insert().values(group_id=group_id, property_id=pid))
    db.commit()
    return get_group(group_id, db)

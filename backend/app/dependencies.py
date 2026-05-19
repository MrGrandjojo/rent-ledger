from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from .auth import decode_token
from .database import get_db
from .models import Lease, Property, User, group_properties, user_groups


# Roles that can view all data globally and manage users/groups/properties.
# 'admin' is additionally the only role allowed to access audit logs.
PRIVILEGED_ROLES = ("admin", "supervisor")

# Endpoints reachable while force_password_change is True. Anything else is
# blocked server-side so a user can't bypass the frontend redirect by hitting
# the API directly.
_PWD_CHANGE_ALLOWED_PATHS = {
    "/api/auth/me",
    "/api/auth/logout",
    "/api/auth/change-password",
}


def has_global_access(user: User) -> bool:
    return user.role in PRIVILEGED_ROLES


def get_current_user(
    request: Request,
    access_token: str = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    username = decode_token(access_token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé")
    if user.force_password_change and request.url.path not in _PWD_CHANGE_ALLOWED_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Changement de mot de passe requis",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Strict admin gate — used only for audit-log endpoints. Supervisors
    cannot pass this check."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès administrateur requis")
    return user


def require_admin_or_supervisor(user: User = Depends(get_current_user)) -> User:
    """Gate for management endpoints — admins and supervisors only."""
    if not has_global_access(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès administrateur requis")
    return user


def accessible_property_ids(db: Session, user: User) -> set[int] | None:
    """Return the set of property IDs the user can access.

    Returns None for privileged users (admin/supervisor — "all properties,
    no filtering"). Regular users get the union of property IDs across their
    groups.
    """
    if has_global_access(user):
        return None
    rows = (
        db.query(group_properties.c.property_id)
        .join(user_groups, user_groups.c.group_id == group_properties.c.group_id)
        .filter(user_groups.c.user_id == user.id)
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def assert_property_access(db: Session, user: User, property_id: int) -> Property:
    """Return the property if accessible, else raise 404 (never 403, to avoid
    leaking the existence of out-of-scope properties)."""
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(404, "Bien introuvable")
    if has_global_access(user):
        return prop
    ids = accessible_property_ids(db, user)
    if property_id not in (ids or set()):
        raise HTTPException(404, "Bien introuvable")
    return prop


def assert_lease_access(db: Session, user: User, lease_id: int) -> Lease:
    """Return the lease if its property is accessible, else 404."""
    lease = db.get(Lease, lease_id)
    if not lease:
        raise HTTPException(404, "Bail introuvable")
    if has_global_access(user):
        return lease
    ids = accessible_property_ids(db, user)
    if lease.property_id not in (ids or set()):
        raise HTTPException(404, "Bail introuvable")
    return lease

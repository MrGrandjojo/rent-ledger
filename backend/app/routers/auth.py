from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..audit_log import log_event
from ..auth import create_access_token, hash_password, verify_password
from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import User, UserProfile
from ..rate_limit import limiter
from ..schemas import ChangePasswordRequest, LoginRequest, ProfileLite, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/login")
@limiter.limit(settings.login_rate_limit)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    ip = _client_ip(request)
    if not user or not verify_password(req.password, user.password_hash):
        # Failed login is always audited — primary signal for brute-force attempts.
        log_event(
            db, None,
            user_display_name=req.username or "?",
            action="login_failed", entity_type="auth",
            entity_label=req.username,
            ip_address=ip or None,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides")
    if not user.is_active:
        log_event(
            db, user,
            action="login_failed", entity_type="auth",
            entity_label=user.username,
            after={"reason": "inactive"},
            ip_address=ip or None,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé")
    token = create_access_token({"sub": user.username})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    # Only admin successful logins are audited; regular users / supervisors
    # stay quiet to avoid log noise. Logout is never audited.
    if user.role == "admin":
        log_event(
            db, user,
            action="login", entity_type="auth",
            entity_label=user.username,
            ip_address=ip or None,
        )
    return {"force_password_change": user.force_password_change}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = db.get(UserProfile, current_user.id)
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        force_password_change=current_user.force_password_change,
        profile=ProfileLite.model_validate(profile) if profile else None,
    )


@router.put("/change-password")
def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    current_user.password_hash = hash_password(req.new_password)
    current_user.force_password_change = False
    db.commit()
    return {"ok": True}

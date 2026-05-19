"""Per-user landlord profile + encrypted signature.

Replaces the v1.x global /api/settings endpoint. Each authenticated user owns
their profile and (optional) signature; both are used when generating rent
receipts on their behalf.

Security guarantees:
- The plaintext signature is read into memory once on upload, immediately
  encrypted (AES-256-GCM), and never written to disk. Only the encrypted
  base64 string ends up in user_profiles.signature_encrypted.
- The /preview endpoint decrypts in memory, downscales + blurs via Pillow,
  and streams the resulting PNG back. No temp file is created.
"""

from io import BytesIO
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from PIL import Image, ImageFilter
from sqlalchemy.orm import Session

from ..crypto import decrypt_signature, encrypt_signature
from ..database import get_db
from ..dependencies import get_current_user
from ..models import User, UserProfile
from ..schemas import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/api/profile", tags=["profile"])

MAX_SIGNATURE_BYTES = 500 * 1024  # 500 KB
ALLOWED_MIME = {"image/png", "image/jpeg"}


def _get_or_create_profile(db: Session, user: User) -> UserProfile:
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _to_out(profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        landlord_name=profile.landlord_name or "",
        landlord_address=profile.landlord_address or "",
        landlord_phone=profile.landlord_phone or "",
        landlord_email=profile.landlord_email or "",
        has_signature=bool(profile.signature_encrypted),
    )


@router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = _get_or_create_profile(db, user)
    return _to_out(profile)


@router.put("", response_model=ProfileOut)
def update_profile(
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = _get_or_create_profile(db, user)
    profile.landlord_name = body.landlord_name
    profile.landlord_address = body.landlord_address
    profile.landlord_phone = body.landlord_phone
    profile.landlord_email = body.landlord_email
    db.commit()
    db.refresh(profile)
    return _to_out(profile)


@router.post("/signature", response_model=ProfileOut)
async def upload_signature(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, "Format invalide — PNG ou JPG uniquement")

    content = await file.read()
    if len(content) > MAX_SIGNATURE_BYTES:
        raise HTTPException(400, "Fichier trop volumineux — 500 KB maximum")
    if not content:
        raise HTTPException(400, "Fichier vide")

    # Validate and re-encode as PNG to strip EXIF / ICC / other metadata that
    # a scanned signature photo might carry (GPS, device serials, etc.).
    try:
        with Image.open(BytesIO(content)) as img:
            img.load()
            sanitized = BytesIO()
            img.convert("RGBA").save(sanitized, format="PNG")
            payload = sanitized.getvalue()
    except Exception:
        raise HTTPException(400, "Image illisible")

    profile = _get_or_create_profile(db, user)
    profile.signature_encrypted = encrypt_signature(payload)
    db.commit()
    db.refresh(profile)
    return _to_out(profile)


@router.delete("/signature", status_code=status.HTTP_204_NO_CONTENT)
def delete_signature(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = _get_or_create_profile(db, user)
    profile.signature_encrypted = None
    db.commit()


@router.get("/signature/preview")
def signature_preview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return a blurred, downscaled PNG preview generated entirely in memory."""
    profile = _get_or_create_profile(db, user)
    if not profile.signature_encrypted:
        raise HTTPException(404, "Aucune signature enregistrée")

    plaintext = decrypt_signature(profile.signature_encrypted)
    buf = BytesIO()
    with Image.open(BytesIO(plaintext)) as img:
        img = img.convert("RGBA")
        # Downscale to ~80 px tall to obscure detail before blurring.
        target_h = 80
        if img.height > target_h:
            scale = target_h / img.height
            img = img.resize((max(1, int(img.width * scale)), target_h), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=6))
        img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")

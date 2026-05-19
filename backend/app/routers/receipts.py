"""Rent receipt (quittance de loyer) PDF generation endpoint.

The landlord block and signature come from the authenticated user's profile
(not a global config). The signature, if any, is decrypted in memory just
before PDF rendering and goes out of scope at the end of the request — never
touched by the filesystem.
"""

import os
import re
import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings as app_settings
from ..crypto import decrypt_signature
from ..database import get_db
from ..dependencies import assert_lease_access, get_current_user
from ..lease_rules import effective_revision_for
from ..models import Document, Lease, Payment, Property, Tenant, User, UserProfile
from ..pdf_generator import generate_rent_receipt

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s or "").strip("-").lower() or "locataire"


@router.post("/generate/{lease_id}")
def generate_receipt(
    lease_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lease = assert_lease_access(db, current_user, lease_id)

    property_ = db.get(Property, lease.property_id)
    tenant = db.get(Tenant, lease.tenant_id)
    profile = db.get(UserProfile, current_user.id)

    payment = db.query(Payment).filter_by(
        lease_id=lease_id, year=year, month=month
    ).first()

    payment_date_str = (
        payment.payment_date.strftime("%d/%m/%Y")
        if payment and payment.payment_date
        else date.today().strftime("%d/%m/%Y")
    )

    property_address = (
        f"{property_.address_street}, {property_.address_zip} {property_.address_city}"
        if property_ else "—"
    )

    # Rent/charges as of the revision in effect for the receipt period.
    # rent_revisions is the sole source of truth — no fallback to the lease.
    rev = effective_revision_for(db, lease_id, year, month)
    if rev is None:
        raise HTTPException(
            500, "Aucune révision de loyer pour ce bail — incohérence de données"
        )
    rent_for_period = rev.monthly_rent
    charges_for_period = rev.monthly_charges

    # Decrypt signature in memory only — never written to disk.
    signature_bytes = None
    if profile and profile.signature_encrypted:
        signature_bytes = decrypt_signature(profile.signature_encrypted)

    pdf_bytes = generate_rent_receipt(
        landlord_name=profile.landlord_name if profile else "",
        landlord_address=profile.landlord_address if profile else "",
        landlord_phone=profile.landlord_phone if profile else "",
        landlord_email=profile.landlord_email if profile else "",
        tenant_first_name=tenant.first_name if tenant else "",
        tenant_last_name=tenant.last_name if tenant else "",
        property_address=property_address,
        year=year,
        month=month,
        monthly_rent=rent_for_period,
        monthly_charges=charges_for_period,
        payment_date=payment_date_str,
        signature_png_bytes=signature_bytes,
    )
    # Drop the reference; the bytes go out of scope at function return.
    signature_bytes = None

    tenant_slug = _slug(tenant.last_name) if tenant else "locataire"
    short_uuid = uuid.uuid4().hex[:8]
    filename = f"quittance_{month:02d}-{year}_{tenant_slug}_{short_uuid}.pdf"

    dest = os.path.join(app_settings.upload_dir, filename)
    os.makedirs(app_settings.upload_dir, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(pdf_bytes)

    doc = Document(
        lease_id=lease_id,
        type="rent_receipt",
        file_name=filename,
        stored_path=filename,
    )
    db.add(doc)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

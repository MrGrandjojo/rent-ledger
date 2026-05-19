import os
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_lease_access, get_current_user,
    has_global_access,
)
from ..models import Document, Lease, User
from ..schemas import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_TYPES = {"rent_receipt", "lease_scan", "other"}


def _doc_visible(db: Session, user: User, doc: Document) -> bool:
    if has_global_access(user):
        return True
    ids = accessible_property_ids(db, user) or set()
    lease = db.get(Lease, doc.lease_id)
    return bool(lease and lease.property_id in ids)


@router.get("", response_model=list[DocumentOut])
def list_documents(lease_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Document)
    if lease_id is not None:
        assert_lease_access(db, user, lease_id)
        q = q.filter(Document.lease_id == lease_id)
    else:
        ids = accessible_property_ids(db, user)
        if ids is not None:
            if not ids:
                return []
            q = q.join(Lease, Lease.id == Document.lease_id).filter(Lease.property_id.in_(ids))
    return q.order_by(Document.upload_date.desc()).all()


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    lease_id: int = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_lease_access(db, user, lease_id)
    if doc_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Type de document invalide")

    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(settings.upload_dir, stored_name)
    os.makedirs(settings.upload_dir, exist_ok=True)

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    doc = Document(
        lease_id=lease_id,
        type=doc_type,
        file_name=file.filename or stored_name,
        stored_path=stored_name,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{doc_id}/download")
def download_document(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc or not _doc_visible(db, user, doc):
        raise HTTPException(404, "Document introuvable")
    path = os.path.join(settings.upload_dir, doc.stored_path)
    if not os.path.exists(path):
        raise HTTPException(404, "Fichier introuvable sur le disque")
    return FileResponse(path, filename=doc.file_name)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if not doc or not _doc_visible(db, user, doc):
        raise HTTPException(404, "Document introuvable")
    path = os.path.join(settings.upload_dir, doc.stored_path)
    if os.path.exists(path):
        os.remove(path)
    db.delete(doc)
    db.commit()

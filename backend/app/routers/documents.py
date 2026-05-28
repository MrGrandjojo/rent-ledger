import os
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..audit_log import log_event, snapshot_row
from ..config import settings
from ..database import get_db
from ..dependencies import (
    accessible_property_ids, assert_lease_access, get_current_user,
    has_global_access,
)
from ..models import Document, Lease, User
from ..schemas import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_TYPES = {"rent_receipt", "lease_scan", "commandement_payer", "other"}

_DOCUMENT_FIELDS = ["id", "lease_id", "type", "file_name", "stored_path"]

# 25 MB cap on uploads — covers a scanned multi-page PDF lease comfortably
# while preventing single-process memory exhaustion. Nginx must also enforce
# `client_max_body_size 25M` so oversize requests are rejected at the edge
# before reaching uvicorn.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Magic-number prefixes we accept. Extension is unreliable (and trivially
# spoofable); content sniffing is the actual gate. PNG/JPG kept because
# scans are sometimes saved as images, even for lease docs.
_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-",                     "pdf"),
    (b"\x89PNG\r\n\x1a\n",         "png"),
    (b"\xff\xd8\xff",              "jpg"),
)


def _sniff_kind(content: bytes) -> str | None:
    for prefix, kind in _MAGIC_PREFIXES:
        if content.startswith(prefix):
            return kind
    return None


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

    # Early size gate via Content-Length when the client provides it —
    # avoids reading multi-GB bodies into memory before realising they're
    # over the cap. The streamed read below is the second line of defence
    # for clients that lie about the header.
    declared = file.size if hasattr(file, "size") else None
    if declared is not None and declared > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Fichier trop volumineux ({declared // 1024} KB > "
            f"{MAX_UPLOAD_BYTES // 1024} KB)",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"Fichier trop volumineux (> {MAX_UPLOAD_BYTES // 1024} KB)"
        )

    kind = _sniff_kind(content)
    if kind is None:
        raise HTTPException(
            415, "Format non supporté — PDF, PNG ou JPG uniquement"
        )

    # Use the sniffed type for the stored extension, not the user-provided
    # one — defends against `evil.pdf` that's actually HTML/JS or the
    # reverse.
    stored_name = f"{uuid.uuid4().hex}.{kind}"
    dest = os.path.join(settings.upload_dir, stored_name)
    os.makedirs(settings.upload_dir, exist_ok=True)

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
    log_event(
        db, user, action="create", entity_type="document",
        entity_id=str(doc.id), entity_label=doc.file_name,
        after=snapshot_row(doc, _DOCUMENT_FIELDS),
    )
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
    before = snapshot_row(doc, _DOCUMENT_FIELDS)
    label = doc.file_name
    path = os.path.join(settings.upload_dir, doc.stored_path)
    if os.path.exists(path):
        os.remove(path)
    db.delete(doc)
    db.commit()
    log_event(
        db, user, action="delete", entity_type="document",
        entity_id=str(doc_id), entity_label=label, before=before,
    )

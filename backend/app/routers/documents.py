import json
from pathlib import Path

from anyio import to_thread
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Document, DocumentChunk, IngestionJob, User
from app.queue import enqueue_ingestion
from app.schemas import DocumentOut, DocumentReviewOut, DocumentStatusOut, ParsedBlockOut, ReviewChunkOut
from app.services.permissions import can_access_document
from app.services.ingestion_progress import init_progress, load_progress
from app.services.storage import document_artifact_dir, original_file_path, remove_document_files


router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".png", ".jpg", ".jpeg"}


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filename = Path(file.filename or "document").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")

    document = Document(
        filename=filename,
        mime_type=file.content_type,
        size_bytes=0,
        storage_path="pending",
        status="queued",
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.flush()

    target_path = original_file_path(document.id)
    size = 0
    with target_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_upload_bytes:
                db.rollback()
                remove_document_files(document.id)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {settings.max_upload_mb} MB limit",
                )
            out.write(chunk)

    document.storage_path = str(target_path)
    document.size_bytes = size
    job = IngestionJob(document_id=document.id, status="queued")
    db.add(job)
    db.commit()
    init_progress(document.id, document.filename)
    db.refresh(document)

    try:
        enqueue_ingestion(document.id)
    except Exception as exc:
        if settings.sync_ingestion_on_queue_failure:
            from app.worker import ingest_document

            await to_thread.run_sync(ingest_document, document.id)
            db.refresh(document)
        else:
            document.status = "failed"
            document.error_message = f"Could not enqueue ingestion job: {exc}"
            job.status = "failed"
            job.error_message = document.error_message
            db.commit()
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Document).order_by(Document.created_at.desc())
    if current_user.role != "admin":
        query = query.filter(Document.uploaded_by == current_user.id)
    return query.all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.query(Document).filter(Document.id == document_id).one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access_document(current_user, document):
        raise HTTPException(status_code=403, detail="Access denied")
    return document


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def get_document_status(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.query(Document).filter(Document.id == document_id).one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access_document(current_user, document):
        raise HTTPException(status_code=403, detail="Access denied")
    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == document.id)
        .order_by(IngestionJob.created_at.desc())
        .first()
    )
    return DocumentStatusOut(
        document_id=document.id,
        status=document.status,
        page_count=document.page_count,
        error_message=document.error_message,
        job_status=job.status if job else None,
        steps=load_progress(document.id).get("steps", []),
    )


@router.get("/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.query(Document).filter(Document.id == document_id).one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access_document(current_user, document):
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(document.storage_path, media_type=document.mime_type, filename=document.filename)


@router.get("/{document_id}/review", response_model=DocumentReviewOut)
def review_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.query(Document).filter(Document.id == document_id).one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access_document(current_user, document):
        raise HTTPException(status_code=403, detail="Access denied")

    parsed_blocks = _load_parsed_blocks(document.id)
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.page_number.asc(), DocumentChunk.chunk_index.asc())
        .all()
    )
    parser_names = sorted(
        {
            str(block.metadata.get("parser"))
            for block in parsed_blocks
            if block.metadata and block.metadata.get("parser")
        }
    )
    return DocumentReviewOut(
        document=document,
        parsed_blocks=parsed_blocks,
        chunks=[
            ReviewChunkOut(
                id=chunk.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content_type=chunk.content_type,
                token_count=chunk.token_count,
                content=chunk.content,
                metadata=chunk.metadata_json or {},
            )
            for chunk in chunks
        ],
        parsed_block_count=len(parsed_blocks),
        chunk_count=len(chunks),
        total_tokens=sum(chunk.token_count for chunk in chunks),
        parser_names=parser_names,
    )


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = db.query(Document).filter(Document.id == document_id).one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not can_access_document(current_user, document):
        raise HTTPException(status_code=403, detail="Access denied")
    db.delete(document)
    db.commit()
    remove_document_files(document.id)
    return {"ok": True}


def _load_parsed_blocks(document_id: str) -> list[ParsedBlockOut]:
    parsed_path = document_artifact_dir(document_id) / "parsed.json"
    if not parsed_path.exists():
        return []
    try:
        data = json.loads(parsed_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    blocks = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        blocks.append(
            ParsedBlockOut(
                page_number=int(item.get("page_number") or 1),
                block_type=str(item.get("block_type") or item.get("type") or "text"),
                content=content,
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
        )
    return blocks

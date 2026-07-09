from datetime import datetime

from redis import Redis
from rq import Worker

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Document, DocumentChunk, IngestionJob, PageIndex
from app.queue import QUEUE_NAME
from app.services.chunking import blocks_to_chunks
from app.services.embeddings import embed_texts
from app.services.pageindex import build_page_index
from app.services.parsing import parse_document


settings = get_settings()


def ingest_document(document_id: str) -> None:
    import asyncio

    db = SessionLocal()
    job = None
    try:
        document = db.query(Document).filter(Document.id == document_id).one()
        job = (
            db.query(IngestionJob)
            .filter(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .first()
        )
        if job:
            job.status = "processing"
            job.started_at = datetime.utcnow()
        document.status = "processing"
        document.error_message = None
        db.commit()

        blocks, page_count = asyncio.run(
            parse_document(document.id, document.storage_path_as_path, document.filename, document.mime_type or "")
        )
        chunks = blocks_to_chunks(document.id, blocks)
        embeddings = embed_texts([chunk.content for chunk in chunks])

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.flush()
        db_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            db_chunk = DocumentChunk(
                document_id=document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_type=chunk.content_type,
                token_count=chunk.token_count,
                embedding=embedding,
                metadata_json=chunk.metadata,
            )
            db.add(db_chunk)
            db_chunks.append(db_chunk)
        document.page_count = page_count
        document.status = "ready"

        if page_count >= settings.pageindex_min_pages:
            db.flush()
            tree = build_page_index(document.id, document.storage_path_as_path, db_chunks)
            page_index = db.query(PageIndex).filter(PageIndex.document_id == document.id).one_or_none()
            if page_index is None:
                page_index = PageIndex(document_id=document.id)
                db.add(page_index)
            page_index.status = "ready"
            page_index.tree_json = tree
            page_index.error_message = None

        if job:
            job.status = "ready"
            job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        document = db.query(Document).filter(Document.id == document_id).one_or_none()
        if document:
            document.status = "failed"
            document.error_message = str(exc)[:1000]
        if job:
            job.status = "failed"
            job.error_message = str(exc)[:1000]
            job.finished_at = datetime.utcnow()
        db.commit()
        raise
    finally:
        db.close()


def main() -> None:
    init_db()
    redis_conn = Redis.from_url(settings.redis_url)
    worker = Worker([QUEUE_NAME], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()

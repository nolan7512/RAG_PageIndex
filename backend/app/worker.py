from datetime import datetime

from redis import Redis
from rq import Worker

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Document, DocumentChunk, IngestionJob, PageIndex
from app.queue import QUEUE_NAME
from app.services.chunking import blocks_to_chunks
from app.services.embeddings import embed_texts
from app.services.ingestion_progress import fail_progress, mark_step
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

        mark_step(document.id, "parsing", "processing", "Parsing document into normalized content blocks.")
        blocks, page_count = asyncio.run(
            parse_document(document.id, document.storage_path_as_path, document.filename, document.mime_type or "")
        )
        parser_names = sorted({str(block.metadata.get("parser")) for block in blocks if block.metadata.get("parser")})
        mark_step(
            document.id,
            "parsing",
            "done",
            f"Parsed {len(blocks)} content blocks.",
            {"block_count": len(blocks), "page_count": page_count, "parsers": parser_names},
        )
        ocr_blocks = [block for block in blocks if "ocr" in str(block.metadata.get("parser", "")).lower()]
        mark_step(
            document.id,
            "ocr",
            "done" if ocr_blocks else "skipped",
            f"OCR produced {len(ocr_blocks)} page blocks." if ocr_blocks else "No OCR step was required.",
            {"ocr_block_count": len(ocr_blocks), "parsers": parser_names},
        )

        mark_step(document.id, "chunking", "processing", "Splitting parsed content into retrieval chunks.")
        chunks = blocks_to_chunks(document.id, blocks)
        mark_step(
            document.id,
            "chunking",
            "done",
            f"Created {len(chunks)} chunks.",
            {"chunk_count": len(chunks), "token_count": sum(chunk.token_count for chunk in chunks)},
        )

        mark_step(document.id, "embedding", "processing", "Creating embeddings for chunks.")
        embeddings = embed_texts([chunk.content for chunk in chunks])
        mark_step(
            document.id,
            "embedding",
            "done",
            f"Created {len(embeddings)} embeddings.",
            {"embedding_count": len(embeddings), "model": settings.openai_embedding_model},
        )

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
            mark_step(document.id, "pageindex", "processing", "Building page index for long document.")
            db.flush()
            tree = build_page_index(document.id, document.storage_path_as_path, db_chunks)
            page_index = db.query(PageIndex).filter(PageIndex.document_id == document.id).one_or_none()
            if page_index is None:
                page_index = PageIndex(document_id=document.id)
                db.add(page_index)
            page_index.status = "ready"
            page_index.tree_json = tree
            page_index.error_message = None
            mark_step(document.id, "pageindex", "done", "Page index is ready.")
        else:
            mark_step(
                document.id,
                "pageindex",
                "skipped",
                f"Skipped because page count is below {settings.pageindex_min_pages}.",
                {"page_count": page_count, "threshold": settings.pageindex_min_pages},
            )

        if job:
            job.status = "ready"
            job.finished_at = datetime.utcnow()
        mark_step(document.id, "ready", "done", "Document is ready for search and chat.")
        db.commit()
    except Exception as exc:
        db.rollback()
        document = db.query(Document).filter(Document.id == document_id).one_or_none()
        if document:
            document.status = "failed"
            document.error_message = str(exc)[:1000]
            fail_progress(document.id, str(exc)[:1000])
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

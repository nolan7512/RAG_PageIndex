import math
from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentChunk, PageIndex, User
from app.services.chunking import excerpt
from app.services.embeddings import embed_text
from app.services.pageindex import page_boosts_from_tree
from app.services.vietnamese import lexical_score, tokenize_vietnamese_query


settings = get_settings()


@dataclass
class RetrievedChunk:
    chunk: DocumentChunk
    document: Document
    score: float
    lexical_score: float = 0.0


def retrieve_chunks(db: Session, user: User, query: str, limit: int = 8, candidates: int = 30) -> List[RetrievedChunk]:
    query_embedding = embed_text(query)
    semantic = _semantic_search(db, user, query_embedding, candidates)
    keyword = _keyword_search(db, user, query, candidates)

    by_id = {}
    for result in semantic + keyword:
        existing = by_id.get(result.chunk.id)
        if existing is None or result.score > existing.score:
            by_id[result.chunk.id] = result

    boosted = list(by_id.values())
    _apply_pageindex_boosts(db, query, boosted)
    boosted.sort(key=lambda item: item.score, reverse=True)
    for result in boosted:
        result.lexical_score = max(result.lexical_score, lexical_score(query, result.chunk.content))
    return boosted[:limit]


def result_to_dict(result: RetrievedChunk):
    return {
        "document_id": result.document.id,
        "filename": result.document.filename,
        "page_number": result.chunk.page_number,
        "chunk_id": result.chunk.id,
        "excerpt": excerpt(result.chunk.content),
        "score": round(float(result.score), 4),
        "lexical_score": round(float(result.lexical_score), 4),
    }


def _visible_documents_query(db: Session, user: User):
    query = db.query(Document)
    if user.role != "admin":
        query = query.filter(Document.uploaded_by == user.id)
    return query


def _semantic_search(db: Session, user: User, query_embedding: List[float], candidates: int) -> List[RetrievedChunk]:
    if settings.is_postgres:
        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        rows = (
            db.query(DocumentChunk, Document, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(Document.status == "ready")
            .filter(DocumentChunk.embedding.is_not(None))
        )
        if user.role != "admin":
            rows = rows.filter(Document.uploaded_by == user.id)
        rows = rows.order_by(distance).limit(candidates).all()
        return [
            RetrievedChunk(chunk=chunk, document=document, score=max(0.0, 1.0 - float(distance_value or 1.0)))
            for chunk, document, distance_value in rows
        ]

    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(Document.status == "ready")
        .filter(DocumentChunk.embedding.is_not(None))
        .all()
    )
    results = []
    for chunk, document in rows:
        if user.role != "admin" and document.uploaded_by != user.id:
            continue
        results.append(
            RetrievedChunk(
                chunk=chunk,
                document=document,
                score=_cosine_similarity(query_embedding, chunk.embedding or []),
            )
        )
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:candidates]


def _keyword_search(db: Session, user: User, query: str, candidates: int) -> List[RetrievedChunk]:
    terms = tokenize_vietnamese_query(query)
    if not terms:
        return []

    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(Document.status == "ready")
    )
    if user.role != "admin":
        rows = rows.filter(Document.uploaded_by == user.id)
    rows = rows.limit(max(candidates * 20, 200)).all()

    results = []
    for chunk, document in rows:
        score = lexical_score(query, chunk.content)
        if score > 0:
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    document=document,
                    score=min(0.88, 0.42 + score * 0.46),
                    lexical_score=score,
                )
            )
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:candidates]


def _apply_pageindex_boosts(db: Session, query: str, results: List[RetrievedChunk]) -> None:
    document_ids = list({result.document.id for result in results})
    if not document_ids:
        return
    page_indexes = db.query(PageIndex).filter(PageIndex.document_id.in_(document_ids)).all()
    boosts_by_doc = {
        page_index.document_id: page_boosts_from_tree(query, page_index.tree_json or {})
        for page_index in page_indexes
        if page_index.status == "ready"
    }
    for result in results:
        boost = boosts_by_doc.get(result.document.id, {}).get(result.chunk.page_number, 0.0)
        result.score += boost


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)

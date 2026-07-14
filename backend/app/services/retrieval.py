import math
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Collection, Document, DocumentChunk, FolderNode, PageIndex, RelatedDocument, StructureIndex, User
from app.services.chunking import excerpt
from app.services.embeddings import embed_text
from app.services.hierarchy import STRUCTURE_ROUTE_TOP_K
from app.services.pageindex import page_boosts_from_tree
from app.services.reranking import rerank_scores
from app.services.vietnamese import lexical_score, tokenize_vietnamese_query


settings = get_settings()


@dataclass
class RetrievedChunk:
    chunk: DocumentChunk
    document: Document
    score: float
    lexical_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class RetrievalScope:
    scope_type: str = "all"
    scope_id: Optional[str] = None
    collection_id: Optional[str] = None
    folder: Optional[FolderNode] = None
    document_id: Optional[str] = None


def retrieve_chunks(
    db: Session,
    user: User,
    query: str,
    limit: int = 8,
    candidates: int = 30,
    scope_type: str = "all",
    scope_id: Optional[str] = None,
) -> List[RetrievedChunk]:
    scope = resolve_scope(db, user, scope_type, scope_id)
    query_embedding = embed_text(query)
    route_paths = _route_folder_paths(db, user, query_embedding, scope)
    semantic = _semantic_search(db, user, query_embedding, candidates, scope, route_paths)
    keyword = _keyword_search(db, user, query, candidates, scope, route_paths)
    combined = _merge_results(semantic + keyword)

    if not combined and route_paths:
        semantic = _semantic_search(db, user, query_embedding, candidates, scope, [])
        keyword = _keyword_search(db, user, query, candidates, scope, [])
        combined = _merge_results(semantic + keyword)

    boosted = list(combined.values())
    _apply_pageindex_boosts(db, query, boosted)
    _apply_related_document_boosts(db, boosted)
    boosted.sort(key=lambda item: item.score, reverse=True)
    for result in boosted:
        result.lexical_score = max(result.lexical_score, lexical_score(query, result.chunk.content))
    _apply_reranker(query, boosted)
    boosted.sort(key=lambda item: item.score, reverse=True)
    return boosted[:limit]


def _merge_results(results: List[RetrievedChunk]) -> dict:
    by_id = {}
    for result in results:
        existing = by_id.get(result.chunk.id)
        if existing is None or result.score > existing.score:
            by_id[result.chunk.id] = result
    return by_id


def result_to_dict(result: RetrievedChunk):
    return {
        "document_id": result.document.id,
        "filename": result.document.filename,
        "relative_path": result.document.relative_path or result.document.filename,
        "folder_path": result.document.folder_path or "",
        "page_number": result.chunk.page_number,
        "chunk_id": result.chunk.id,
        "excerpt": excerpt(result.chunk.content),
        "score": round(float(result.score), 4),
        "lexical_score": round(float(result.lexical_score), 4),
        "rerank_score": round(float(result.rerank_score), 4),
    }


def _visible_documents_query(db: Session, user: User):
    query = db.query(Document)
    if user.role != "admin":
        query = query.filter(Document.uploaded_by == user.id)
    return query


def resolve_scope(db: Session, user: User, scope_type: str = "all", scope_id: Optional[str] = None) -> RetrievalScope:
    scope_type = (scope_type or "all").lower()
    if scope_type not in {"all", "collection", "folder", "document"}:
        raise ValueError("Invalid scope_type")
    if scope_type == "all":
        return RetrievalScope(scope_type="all")
    if not scope_id:
        raise ValueError("scope_id is required for scoped search")

    if scope_type == "collection":
        collection = db.query(Collection).filter(Collection.id == scope_id).one_or_none()
        if collection is None or (user.role != "admin" and collection.created_by != user.id):
            raise ValueError("Collection not found or not accessible")
        return RetrievalScope(scope_type=scope_type, scope_id=scope_id, collection_id=collection.id)

    if scope_type == "folder":
        folder = db.query(FolderNode).join(Collection, Collection.id == FolderNode.collection_id).filter(FolderNode.id == scope_id).one_or_none()
        if folder is None or (user.role != "admin" and folder.collection.created_by != user.id):
            raise ValueError("Folder not found or not accessible")
        return RetrievalScope(scope_type=scope_type, scope_id=scope_id, collection_id=folder.collection_id, folder=folder)

    document = db.query(Document).filter(Document.id == scope_id).one_or_none()
    if document is None or (user.role != "admin" and document.uploaded_by != user.id):
        raise ValueError("Document not found or not accessible")
    return RetrievalScope(
        scope_type=scope_type,
        scope_id=scope_id,
        collection_id=document.collection_id,
        document_id=document.id,
    )


def _semantic_search(
    db: Session,
    user: User,
    query_embedding: List[float],
    candidates: int,
    scope: RetrievalScope,
    route_paths: list[tuple[str, str]],
) -> List[RetrievedChunk]:
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
        rows = _apply_scope_filters(rows, scope)
        rows = _apply_route_filters(rows, route_paths)
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
    )
    if user.role != "admin":
        rows = rows.filter(Document.uploaded_by == user.id)
    rows = _apply_scope_filters(rows, scope)
    rows = _apply_route_filters(rows, route_paths).all()
    results = []
    for chunk, document in rows:
        results.append(
            RetrievedChunk(
                chunk=chunk,
                document=document,
                score=_cosine_similarity(query_embedding, chunk.embedding or []),
            )
        )
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:candidates]


def _keyword_search(
    db: Session,
    user: User,
    query: str,
    candidates: int,
    scope: RetrievalScope,
    route_paths: list[tuple[str, str]],
) -> List[RetrievedChunk]:
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
    rows = _apply_scope_filters(rows, scope)
    rows = _apply_route_filters(rows, route_paths)
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


def _apply_related_document_boosts(db: Session, results: List[RetrievedChunk]) -> None:
    document_ids = list({result.document.id for result in results})
    if len(document_ids) < 2:
        return
    relations = (
        db.query(RelatedDocument)
        .filter(
            RelatedDocument.source_document_id.in_(document_ids),
            RelatedDocument.target_document_id.in_(document_ids),
        )
        .all()
    )
    if not relations:
        return

    relation_scores = {}
    for relation in relations:
        relation_scores[relation.target_document_id] = max(
            relation_scores.get(relation.target_document_id, 0.0),
            min(0.08, max(0.0, relation.score) * 0.04),
        )

    for result in results:
        result.score += relation_scores.get(result.document.id, 0.0)


def _apply_reranker(query: str, results: List[RetrievedChunk]) -> None:
    if settings.reranker_provider != "local_bge_m3" or not results:
        return
    candidates = results[: max(1, settings.reranker_top_k)]
    scores = rerank_scores(query, [item.chunk.embedding_text or item.chunk.content for item in candidates])
    if not scores or len(scores) != len(candidates):
        return
    min_score = min(scores)
    max_score = max(scores)
    span = max(max_score - min_score, 1e-9)
    for item, raw_score in zip(candidates, scores):
        normalized = (raw_score - min_score) / span
        item.rerank_score = normalized
        item.score = item.score * (1.0 - settings.reranker_weight) + normalized * settings.reranker_weight


def _apply_scope_filters(query, scope: RetrievalScope):
    if scope.scope_type == "collection" and scope.collection_id:
        return query.filter(Document.collection_id == scope.collection_id)
    if scope.scope_type == "folder" and scope.folder is not None:
        if not scope.folder.path:
            return query.filter(Document.collection_id == scope.folder.collection_id)
        return query.filter(
            Document.collection_id == scope.folder.collection_id,
            or_(Document.folder_path == scope.folder.path, Document.folder_path.like(f"{scope.folder.path}/%")),
        )
    if scope.scope_type == "document" and scope.document_id:
        return query.filter(Document.id == scope.document_id)
    return query


def _apply_route_filters(query, route_paths: list[tuple[str, str]]):
    if not route_paths:
        return query
    clauses = []
    for collection_id, folder_path in route_paths:
        if folder_path:
            clauses.append(
                (
                    (Document.collection_id == collection_id)
                    & ((Document.folder_path == folder_path) | Document.folder_path.like(f"{folder_path}/%"))
                )
            )
        else:
            clauses.append(Document.collection_id == collection_id)
    return query.filter(or_(*clauses))


def _route_folder_paths(
    db: Session,
    user: User,
    query_embedding: List[float],
    scope: RetrievalScope,
) -> list[tuple[str, str]]:
    if scope.scope_type == "document":
        return []
    rows_query = (
        db.query(StructureIndex, FolderNode)
        .join(FolderNode, FolderNode.id == StructureIndex.folder_id)
        .join(Collection, Collection.id == StructureIndex.collection_id)
        .filter(StructureIndex.scope_type == "folder", StructureIndex.embedding.is_not(None))
    )
    if user.role != "admin":
        rows_query = rows_query.filter(Collection.created_by == user.id)
    if scope.scope_type == "collection" and scope.collection_id:
        rows_query = rows_query.filter(StructureIndex.collection_id == scope.collection_id)
    elif scope.scope_type == "folder" and scope.folder is not None:
        if scope.folder.path:
            rows_query = rows_query.filter(
                StructureIndex.collection_id == scope.folder.collection_id,
                or_(FolderNode.path == scope.folder.path, FolderNode.path.like(f"{scope.folder.path}/%")),
            )
        else:
            rows_query = rows_query.filter(StructureIndex.collection_id == scope.folder.collection_id)

    if settings.is_postgres:
        distance = StructureIndex.embedding.cosine_distance(query_embedding).label("distance")
        rows = rows_query.add_columns(distance).order_by(distance).limit(STRUCTURE_ROUTE_TOP_K).all()
        scored = [(index, folder, max(0.0, 1.0 - float(distance_value or 1.0))) for index, folder, distance_value in rows]
    else:
        scored = []
        for index, folder in rows_query.all():
            scored.append((index, folder, _cosine_similarity(query_embedding, index.embedding or [])))
        scored.sort(key=lambda item: item[2], reverse=True)
        scored = scored[:STRUCTURE_ROUTE_TOP_K]

    selected = [
        (folder.collection_id, folder.path or "")
        for _index, folder, score in scored
        if score >= 0.35
    ]
    if len(selected) > 1:
        non_root = [item for item in selected if item[1]]
        return non_root or selected
    return selected


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)

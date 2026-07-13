import re
from pathlib import PurePosixPath
from typing import Iterable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    ChunkLink,
    Collection,
    Document,
    DocumentChunk,
    DocumentLink,
    FolderEdge,
    FolderNode,
    RelatedDocument,
    StructureIndex,
    User,
)
from app.services.chunking import excerpt
from app.services.embeddings import OpenAIUnavailable, embed_text


LOOSE_COLLECTION_ROOT = "__loose__"
LOOSE_COLLECTION_NAME = "Tài liệu lẻ"
STRUCTURE_ROUTE_TOP_K = 5


class InvalidRelativePath(ValueError):
    pass


def normalize_relative_path(value: Optional[str], fallback_filename: str = "document") -> str:
    raw = (value or fallback_filename or "document").replace("\\", "/").strip()
    if "\x00" in raw:
        raise InvalidRelativePath("relative_path contains invalid characters")
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("/"):
        raise InvalidRelativePath("relative_path must be relative")

    raw = raw.strip("/")
    if not raw:
        raise InvalidRelativePath("relative_path is required")

    parts = [part.strip() for part in raw.split("/")]
    if any(not part or part in {".", ".."} for part in parts):
        raise InvalidRelativePath("relative_path contains invalid path segments")
    return "/".join(parts)


def root_name_from_relative_path(relative_path: str) -> str:
    return relative_path.split("/", 1)[0] or "Collection"


def can_access_collection(user: User, collection: Collection) -> bool:
    return user.role == "admin" or collection.created_by == user.id


def can_access_folder(user: User, folder: FolderNode) -> bool:
    return folder.collection is not None and can_access_collection(user, folder.collection)


def create_collection(db: Session, user: User, name: str, root_path: str = "") -> Collection:
    clean_name = (name or "Collection").strip()[:255] or "Collection"
    clean_root = normalize_collection_root(root_path or clean_name)
    collection = Collection(name=clean_name, root_path=clean_root, created_by=user.id)
    db.add(collection)
    db.flush()
    get_or_create_folder_node(db, collection, "")
    db.commit()
    db.refresh(collection)
    return collection


def get_or_create_loose_collection(db: Session, user: User) -> Collection:
    collection = (
        db.query(Collection)
        .filter(Collection.created_by == user.id, Collection.root_path == LOOSE_COLLECTION_ROOT)
        .one_or_none()
    )
    if collection is None:
        collection = Collection(name=LOOSE_COLLECTION_NAME, root_path=LOOSE_COLLECTION_ROOT, created_by=user.id)
        db.add(collection)
        db.flush()
    get_or_create_folder_node(db, collection, "")
    return collection


def normalize_collection_root(value: str) -> str:
    if value == LOOSE_COLLECTION_ROOT:
        return value
    return normalize_relative_path(value or "Collection")


def resolve_upload_location(
    db: Session,
    user: User,
    collection_id: Optional[str],
    relative_path: Optional[str],
    filename: str,
) -> tuple[Collection, FolderNode, str, str]:
    normalized_path = normalize_relative_path(relative_path or filename, filename)

    if collection_id:
        collection = db.query(Collection).filter(Collection.id == collection_id).one_or_none()
        if collection is None or not can_access_collection(user, collection):
            raise InvalidRelativePath("collection_id is invalid or not accessible")
    else:
        collection = get_or_create_loose_collection(db, user)

    folder_path = folder_path_for_relative_path(collection, normalized_path)
    folder = get_or_create_folder_node(db, collection, folder_path)
    return collection, folder, normalized_path, folder_path


def folder_path_for_relative_path(collection: Collection, relative_path: str) -> str:
    parts = relative_path.split("/")
    if collection.root_path and collection.root_path != LOOSE_COLLECTION_ROOT:
        root_parts = collection.root_path.split("/")
        if parts[: len(root_parts)] == root_parts:
            parts = parts[len(root_parts) :]
    folder_parts = parts[:-1]
    return "/".join(folder_parts)


def get_or_create_folder_node(db: Session, collection: Collection, folder_path: str) -> FolderNode:
    normalized = "" if not folder_path else normalize_relative_path(folder_path)
    existing = (
        db.query(FolderNode)
        .filter(FolderNode.collection_id == collection.id, FolderNode.path == normalized)
        .one_or_none()
    )
    if existing is not None:
        return existing

    if not normalized:
        folder = FolderNode(collection_id=collection.id, parent_id=None, name=collection.name, path="", depth=0)
        db.add(folder)
        db.flush()
        return folder

    parent_path = str(PurePosixPath(normalized).parent)
    if parent_path == ".":
        parent_path = ""
    parent = get_or_create_folder_node(db, collection, parent_path)
    name = PurePosixPath(normalized).name
    folder = FolderNode(
        collection_id=collection.id,
        parent_id=parent.id,
        name=name,
        path=normalized,
        depth=normalized.count("/") + 1,
    )
    db.add(folder)
    db.flush()
    ensure_folder_edge(db, parent.id, folder.id)
    return folder


def ensure_folder_edge(db: Session, parent_folder_id: str, child_folder_id: str) -> None:
    if (
        db.query(FolderEdge)
        .filter(FolderEdge.parent_folder_id == parent_folder_id, FolderEdge.child_folder_id == child_folder_id)
        .one_or_none()
        is None
    ):
        db.add(FolderEdge(parent_folder_id=parent_folder_id, child_folder_id=child_folder_id))


def ensure_document_link(db: Session, document: Document) -> None:
    if not document.folder_id:
        return
    if (
        db.query(DocumentLink)
        .filter(DocumentLink.folder_id == document.folder_id, DocumentLink.document_id == document.id)
        .one_or_none()
        is None
    ):
        db.add(DocumentLink(folder_id=document.folder_id, document_id=document.id))


def ensure_chunk_link(db: Session, chunk: DocumentChunk) -> None:
    if (
        db.query(ChunkLink)
        .filter(ChunkLink.document_id == chunk.document_id, ChunkLink.chunk_id == chunk.id)
        .one_or_none()
        is None
    ):
        db.add(ChunkLink(document_id=chunk.document_id, chunk_id=chunk.id))


def build_embedding_text(document: Document, content: str, metadata: Optional[dict] = None) -> str:
    metadata = metadata or {}
    path = document.relative_path or document.filename
    section = metadata.get("section_title")
    prefix = f"Tài liệu thuộc [{path}]."
    if section:
        prefix += f" Mục: {section}."
    return f"{prefix}\nNội dung: {content}"


def refresh_structure_indexes_for_document(db: Session, document: Document) -> None:
    if not document.collection_id:
        return
    folder_paths = ancestor_folder_paths(document.folder_path or "")
    for folder_path in folder_paths:
        folder = (
            db.query(FolderNode)
            .filter(FolderNode.collection_id == document.collection_id, FolderNode.path == folder_path)
            .one_or_none()
        )
        if folder is not None:
            refresh_structure_index(db, "folder", document.collection_id, folder.id)
    refresh_structure_index(db, "collection", document.collection_id, None)
    refresh_related_documents(db, document)


def ancestor_folder_paths(folder_path: str) -> list[str]:
    if not folder_path:
        return [""]
    parts = folder_path.split("/")
    paths = [""]
    for index in range(len(parts)):
        paths.append("/".join(parts[: index + 1]))
    return paths


def refresh_structure_index(
    db: Session,
    scope_type: str,
    collection_id: str,
    folder_id: Optional[str],
) -> StructureIndex:
    index = (
        db.query(StructureIndex)
        .filter(
            StructureIndex.scope_type == scope_type,
            StructureIndex.collection_id == collection_id,
            StructureIndex.folder_id.is_(None) if folder_id is None else StructureIndex.folder_id == folder_id,
        )
        .one_or_none()
    )
    if index is None:
        index = StructureIndex(scope_type=scope_type, collection_id=collection_id, folder_id=folder_id)
        db.add(index)

    summary_text, tree_json, ready = build_structure_summary(db, scope_type, collection_id, folder_id)
    index.summary_text = summary_text
    index.tree_json = tree_json
    index.status = "ready" if ready else "partial"
    try:
        index.embedding = embed_text(summary_text) if summary_text.strip() else None
    except OpenAIUnavailable:
        index.status = "partial"
        index.embedding = None
    db.flush()
    return index


def build_structure_summary(
    db: Session,
    scope_type: str,
    collection_id: str,
    folder_id: Optional[str],
) -> tuple[str, dict, bool]:
    collection = db.query(Collection).filter(Collection.id == collection_id).one_or_none()
    folder = db.query(FolderNode).filter(FolderNode.id == folder_id).one_or_none() if folder_id else None
    documents_query = db.query(Document).filter(Document.collection_id == collection_id)
    if scope_type == "folder" and folder is not None:
        documents_query = apply_folder_path_filter(documents_query, folder.path)
    documents = documents_query.order_by(Document.relative_path.asc()).all()
    ready_documents = [document for document in documents if document.status == "ready"]

    chunks_query = db.query(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
    chunks_query = chunks_query.filter(Document.collection_id == collection_id, Document.status == "ready")
    if scope_type == "folder" and folder is not None:
        chunks_query = apply_folder_path_filter(chunks_query, folder.path)
    chunk_rows = (
        chunks_query.order_by(Document.relative_path.asc(), DocumentChunk.page_number.asc(), DocumentChunk.chunk_index.asc())
        .limit(16)
        .all()
    )

    title = collection.name if collection else "Collection"
    if scope_type == "folder" and folder is not None:
        title = f"{collection.name if collection else 'Collection'}/{folder.path}".rstrip("/")

    lines = [f"Scope: {scope_type}", f"Path: {title}", "Documents:"]
    for document in documents[:24]:
        lines.append(f"- {document.relative_path or document.filename} ({document.status}, {document.page_count or 0} trang)")
    lines.append("Representative chunks:")
    for chunk, document in chunk_rows:
        section = (chunk.metadata_json or {}).get("section_title")
        label = f"{document.relative_path or document.filename} p.{chunk.page_number}"
        if section:
            label += f" {section}"
        lines.append(f"- {label}: {excerpt(chunk.content, 220)}")

    child_folders = []
    if scope_type == "collection":
        folder_query = db.query(FolderNode).filter(FolderNode.collection_id == collection_id, FolderNode.depth <= 1)
    elif folder is not None:
        folder_query = db.query(FolderNode).filter(FolderNode.parent_id == folder.id)
    else:
        folder_query = db.query(FolderNode).filter(False)
    for child in folder_query.order_by(FolderNode.path.asc()).all():
        child_folders.append({"id": child.id, "name": child.name, "path": child.path, "depth": child.depth})

    tree_json = {
        "title": title,
        "scope_type": scope_type,
        "collection_id": collection_id,
        "folder_id": folder_id,
        "folders": child_folders,
        "documents": [
            {
                "id": document.id,
                "filename": document.filename,
                "relative_path": document.relative_path or document.filename,
                "status": document.status,
            }
            for document in documents[:50]
        ],
    }
    return "\n".join(lines), tree_json, bool(ready_documents)


def refresh_related_documents(db: Session, document: Document) -> None:
    if not document.collection_id:
        return
    db.query(RelatedDocument).filter(RelatedDocument.source_document_id == document.id).delete()
    peers = (
        db.query(Document)
        .filter(Document.collection_id == document.collection_id, Document.id != document.id)
        .limit(100)
        .all()
    )
    for peer in peers:
        if peer.folder_id == document.folder_id:
            relation_type = "same_folder"
            score = 1.0
        else:
            relation_type = "same_collection"
            score = 0.45
        db.add(
            RelatedDocument(
                source_document_id=document.id,
                target_document_id=peer.id,
                relation_type=relation_type,
                score=score,
            )
        )


def apply_folder_path_filter(query, folder_path: str):
    if not folder_path:
        return query
    return query.filter(or_(Document.folder_path == folder_path, Document.folder_path.like(f"{folder_path}/%")))


def descendants_filter_for_folder(folder: FolderNode):
    if not folder.path:
        return Document.collection_id == folder.collection_id
    return or_(Document.folder_path == folder.path, Document.folder_path.like(f"{folder.path}/%"))


def collection_tree(db: Session, collection: Collection) -> dict:
    folders = db.query(FolderNode).filter(FolderNode.collection_id == collection.id).order_by(FolderNode.depth, FolderNode.path).all()
    documents = (
        db.query(Document)
        .filter(Document.collection_id == collection.id)
        .order_by(Document.relative_path.asc(), Document.created_at.desc())
        .all()
    )
    nodes = {
        folder.id: {
            "id": folder.id,
            "name": folder.name,
            "path": folder.path,
            "depth": folder.depth,
            "children": [],
            "documents": [],
        }
        for folder in folders
    }
    root = next((nodes[folder.id] for folder in folders if folder.path == ""), None)
    if root is None:
        root = {"id": None, "name": collection.name, "path": "", "depth": 0, "children": [], "documents": []}
    for folder in folders:
        if not folder.parent_id or folder.id not in nodes:
            continue
        parent = nodes.get(folder.parent_id)
        if parent is not None:
            parent["children"].append(nodes[folder.id])
    for document in documents:
        target = nodes.get(document.folder_id) or root
        target["documents"].append(
            {
                "id": document.id,
                "filename": document.filename,
                "relative_path": document.relative_path or document.filename,
                "folder_path": document.folder_path or "",
                "status": document.status,
                "page_count": document.page_count,
            }
        )
    return {
        "id": collection.id,
        "name": collection.name,
        "root_path": collection.root_path,
        "created_by": collection.created_by,
        "tree": root,
    }


def visible_collections(db: Session, user: User) -> Iterable[Collection]:
    query = db.query(Collection).order_by(Collection.created_at.desc())
    if user.role != "admin":
        query = query.filter(Collection.created_by == user.id)
    return query.all()

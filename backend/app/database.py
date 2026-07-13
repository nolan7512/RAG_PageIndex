from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401
    from app.security import get_password_hash

    if settings.is_postgres:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    Base.metadata.create_all(bind=engine)
    _ensure_hierarchy_schema()
    if settings.is_postgres:
        _ensure_pgvector_dimension()

    from app.models import User

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == settings.admin_email.lower()).one_or_none()
        if admin is None:
            db.add(
                User(
                    email=settings.admin_email.lower(),
                    password_hash=get_password_hash(settings.admin_password),
                    role="admin",
                )
            )
            db.commit()
        _backfill_loose_collection(db)
    finally:
        db.close()


def _ensure_hierarchy_schema() -> None:
    inspector = inspect(engine)
    columns_by_table = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in ("documents", "document_chunks")
        if inspector.has_table(table_name)
    }

    document_columns = {
        "collection_id": "VARCHAR(36)",
        "folder_id": "VARCHAR(36)",
        "relative_path": "VARCHAR(1024)",
        "folder_path": "VARCHAR(1024)",
    }
    chunk_columns = {
        "collection_id": "VARCHAR(36)",
        "folder_id": "VARCHAR(36)",
        "relative_path": "VARCHAR(1024)",
        "folder_path": "VARCHAR(1024)",
        "embedding_text": "TEXT",
    }

    with engine.begin() as conn:
        for column_name, column_type in document_columns.items():
            if column_name not in columns_by_table.get("documents", set()):
                conn.execute(text(f"ALTER TABLE documents ADD COLUMN {column_name} {column_type}"))
        for column_name, column_type in chunk_columns.items():
            if column_name not in columns_by_table.get("document_chunks", set()):
                conn.execute(text(f"ALTER TABLE document_chunks ADD COLUMN {column_name} {column_type}"))


def _backfill_loose_collection(db) -> None:
    from app.models import ChunkLink, Collection, Document, DocumentLink, FolderNode

    documents = db.query(Document).filter(Document.collection_id.is_(None)).all()
    if not documents:
        return

    collections_by_user = {}
    folders_by_user = {}
    for document in documents:
        collection = collections_by_user.get(document.uploaded_by)
        if collection is None:
            collection = (
                db.query(Collection)
                .filter(Collection.created_by == document.uploaded_by, Collection.root_path == "__loose__")
                .one_or_none()
            )
            if collection is None:
                collection = Collection(name="Tài liệu lẻ", root_path="__loose__", created_by=document.uploaded_by)
                db.add(collection)
                db.flush()
            collections_by_user[document.uploaded_by] = collection

        folder = folders_by_user.get(collection.id)
        if folder is None:
            folder = (
                db.query(FolderNode)
                .filter(FolderNode.collection_id == collection.id, FolderNode.path == "")
                .one_or_none()
            )
            if folder is None:
                folder = FolderNode(collection_id=collection.id, parent_id=None, name=collection.name, path="", depth=0)
                db.add(folder)
                db.flush()
            folders_by_user[collection.id] = folder

        document.collection_id = collection.id
        document.folder_id = folder.id
        document.relative_path = document.relative_path or document.filename
        document.folder_path = document.folder_path or ""

        if (
            db.query(DocumentLink)
            .filter(DocumentLink.folder_id == folder.id, DocumentLink.document_id == document.id)
            .one_or_none()
            is None
        ):
            db.add(DocumentLink(folder_id=folder.id, document_id=document.id))

        for chunk in document.chunks:
            chunk.collection_id = collection.id
            chunk.folder_id = folder.id
            chunk.relative_path = chunk.relative_path or document.relative_path
            chunk.folder_path = chunk.folder_path or ""
            chunk.embedding_text = chunk.embedding_text or chunk.content
            if (
                db.query(ChunkLink)
                .filter(ChunkLink.document_id == document.id, ChunkLink.chunk_id == chunk.id)
                .one_or_none()
                is None
            ):
                db.add(ChunkLink(document_id=document.id, chunk_id=chunk.id))

    db.commit()


def _ensure_pgvector_dimension() -> None:
    expected_type = f"vector({settings.embedding_dimensions})"
    with engine.begin() as conn:
        _ensure_vector_column(conn, "document_chunks", "embedding", expected_type)
        _ensure_vector_column(conn, "structure_indexes", "embedding", expected_type)


def _ensure_vector_column(conn, table_name: str, column_name: str, expected_type: str) -> None:
    current_type = conn.execute(
        text(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = :table_name
              AND n.nspname = 'public'
              AND a.attname = :column_name
              AND NOT a.attisdropped
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    if current_type in (None, expected_type):
        return

    if table_name == "document_chunks":
        conn.execute(text("DELETE FROM document_chunks"))
        conn.execute(text("DELETE FROM page_indexes"))
        conn.execute(text("DELETE FROM structure_indexes"))
        conn.execute(
            text(
                """
                UPDATE documents
                SET status = 'failed',
                    error_message = :message,
                    updated_at = NOW()
                WHERE status IN ('ready', 'processing', 'queued')
                """
            ),
            {
                "message": (
                    f"Embedding dimension changed from {current_type} to {expected_type}. "
                    "Delete and upload this document again to re-index."
                )
            },
        )
    else:
        conn.execute(text(f"DELETE FROM {table_name}"))
    conn.execute(
        text(
            f"ALTER TABLE {table_name} "
            f"ALTER COLUMN {column_name} TYPE vector({settings.embedding_dimensions}) USING NULL"
        )
    )

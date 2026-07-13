from sqlalchemy import create_engine, text
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
    finally:
        db.close()


def _ensure_pgvector_dimension() -> None:
    expected_type = f"vector({settings.embedding_dimensions})"
    with engine.begin() as conn:
        current_type = conn.execute(
            text(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'document_chunks'
                  AND n.nspname = 'public'
                  AND a.attname = 'embedding'
                  AND NOT a.attisdropped
                """
            )
        ).scalar()
        if current_type in (None, expected_type):
            return

        conn.execute(text("DELETE FROM document_chunks"))
        conn.execute(text("DELETE FROM page_indexes"))
        conn.execute(
            text(
                f"ALTER TABLE document_chunks "
                f"ALTER COLUMN embedding TYPE vector({settings.embedding_dimensions}) USING NULL"
            )
        )
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

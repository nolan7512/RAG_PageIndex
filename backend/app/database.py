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

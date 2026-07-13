import uuid
from datetime import datetime
from pathlib import Path

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.config import get_settings
from app.database import Base


settings = get_settings()
EmbeddingColumnType = JSON if settings.is_sqlite else Vector(settings.embedding_dimensions)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=new_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    documents = relationship("Document", back_populates="owner")
    collections = relationship("Collection", back_populates="owner")


class Collection(Base):
    __tablename__ = "collections"

    id = Column(String(36), primary_key=True, default=new_id)
    name = Column(String(255), nullable=False)
    root_path = Column(String(1024), nullable=False, default="")
    created_by = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="collections")
    folders = relationship("FolderNode", back_populates="collection", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="collection")
    structure_indexes = relationship("StructureIndex", back_populates="collection", cascade="all, delete-orphan")


class FolderNode(Base):
    __tablename__ = "folder_nodes"

    id = Column(String(36), primary_key=True, default=new_id)
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    path = Column(String(1024), nullable=False, default="", index=True)
    depth = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    collection = relationship("Collection", back_populates="folders")
    parent = relationship("FolderNode", remote_side=[id], back_populates="children")
    children = relationship("FolderNode", back_populates="parent", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="folder")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=new_id)
    filename = Column(String(512), nullable=False)
    mime_type = Column(String(255), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    storage_path = Column(String(1024), nullable=False)
    status = Column(String(32), nullable=False, default="queued", index=True)
    page_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
    folder_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    relative_path = Column(String(1024), nullable=True)
    folder_path = Column(String(1024), nullable=True, index=True)
    uploaded_by = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="documents")
    collection = relationship("Collection", back_populates="documents")
    folder = relationship("FolderNode", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    ingestion_jobs = relationship("IngestionJob", back_populates="document", cascade="all, delete-orphan")
    page_index = relationship("PageIndex", back_populates="document", cascade="all, delete-orphan", uselist=False)

    @property
    def storage_path_as_path(self) -> Path:
        return Path(self.storage_path)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(String(36), primary_key=True, default=new_id)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    document = relationship("Document", back_populates="ingestion_jobs")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=new_id)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True, index=True)
    folder_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    relative_path = Column(String(1024), nullable=True)
    folder_path = Column(String(1024), nullable=True, index=True)
    page_number = Column(Integer, nullable=False, default=1, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    embedding_text = Column(Text, nullable=True)
    content_type = Column(String(64), nullable=False, default="text")
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(EmbeddingColumnType, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    document = relationship("Document", back_populates="chunks")


class StructureIndex(Base):
    __tablename__ = "structure_indexes"

    id = Column(String(36), primary_key=True, default=new_id)
    scope_type = Column(String(32), nullable=False, index=True)
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="CASCADE"), nullable=True, index=True)
    summary_text = Column(Text, nullable=False, default="")
    tree_json = Column(JSON, nullable=True)
    embedding = Column(EmbeddingColumnType, nullable=True)
    status = Column(String(32), nullable=False, default="queued")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    collection = relationship("Collection", back_populates="structure_indexes")
    folder = relationship("FolderNode")


class FolderEdge(Base):
    __tablename__ = "folder_edges"

    id = Column(String(36), primary_key=True, default=new_id)
    parent_folder_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    child_folder_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DocumentLink(Base):
    __tablename__ = "document_links"

    id = Column(String(36), primary_key=True, default=new_id)
    folder_id = Column(String(36), ForeignKey("folder_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ChunkLink(Base):
    __tablename__ = "chunk_links"

    id = Column(String(36), primary_key=True, default=new_id)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(36), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class RelatedDocument(Base):
    __tablename__ = "related_documents"

    id = Column(String(36), primary_key=True, default=new_id)
    source_document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    target_document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String(64), nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PageIndex(Base):
    __tablename__ = "page_indexes"

    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(32), nullable=False, default="queued")
    tree_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="page_index")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="Untitled")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String(36), primary_key=True, default=new_id)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")

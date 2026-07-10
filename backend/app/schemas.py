from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: str

    model_config = ConfigDict(from_attributes=True)


class DocumentOut(BaseModel):
    id: str
    filename: str
    mime_type: Optional[str]
    size_bytes: int
    status: str
    page_count: int
    error_message: Optional[str]
    uploaded_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusOut(BaseModel):
    document_id: str
    status: str
    page_count: int
    error_message: Optional[str]
    job_status: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class ParsedBlockOut(BaseModel):
    page_number: int
    block_type: str
    content: str
    metadata: Dict[str, Any]


class ReviewChunkOut(BaseModel):
    id: str
    page_number: int
    chunk_index: int
    content_type: str
    token_count: int
    content: str
    metadata: Dict[str, Any]


class DocumentReviewOut(BaseModel):
    document: DocumentOut
    parsed_blocks: List[ParsedBlockOut]
    chunks: List[ReviewChunkOut]
    parsed_block_count: int
    chunk_count: int
    total_tokens: int
    parser_names: List[str]


class CitationOut(BaseModel):
    document_id: str
    filename: str
    page_number: int
    chunk_id: str
    excerpt: str


class SearchRequest(BaseModel):
    query: str
    limit: int = 8


class SearchResultOut(BaseModel):
    document_id: str
    filename: str
    page_number: int
    chunk_id: str
    excerpt: str
    score: float
    lexical_score: float = 0.0
    rerank_score: float = 0.0


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    citations: List[CitationOut]


class ConversationMessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: List[Dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailOut(ConversationOut):
    messages: List[ConversationMessageOut]

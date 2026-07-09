from typing import List, Tuple

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Conversation, ConversationMessage, User
from app.services.chunking import excerpt
from app.services.embeddings import OpenAIUnavailable
from app.services.retrieval import RetrievedChunk, retrieve_chunks


settings = get_settings()

SYSTEM_PROMPT = """You are an internal document assistant.
Answer only from the provided document context.
If the context does not contain enough information, say that the information was not found in the documents.
Do not invent numbers, dates, clauses, or source names.
Use concise Vietnamese by default unless the user asks for another language.
"""


def answer_question(
    db: Session,
    user: User,
    message: str,
    conversation_id: str = None,
) -> Tuple[str, Conversation, List[dict]]:
    retrieved = retrieve_chunks(db, user, message, limit=8)
    conversation = _get_or_create_conversation(db, user, conversation_id, message)
    citations = [_citation_dict(item) for item in retrieved]

    db.add(ConversationMessage(conversation_id=conversation.id, role="user", content=message, citations=[]))
    answer = _generate_answer(message, retrieved)
    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=citations,
        )
    )
    db.commit()
    db.refresh(conversation)
    return answer, conversation, citations


def _get_or_create_conversation(db: Session, user: User, conversation_id: str, message: str) -> Conversation:
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .one_or_none()
        )
        if conversation is not None:
            return conversation

    title = message.strip()[:80] or "New conversation"
    conversation = Conversation(user_id=user.id, title=title)
    db.add(conversation)
    db.flush()
    return conversation


def _generate_answer(message: str, retrieved: List[RetrievedChunk]) -> str:
    if not retrieved:
        return "Không tìm thấy thông tin phù hợp trong các tài liệu hiện có."
    if settings.use_fake_openai:
        return "Đây là câu trả lời giả lập cho môi trường test. Vui lòng cấu hình OPENAI_API_KEY để dùng mô hình thật."
    if not settings.openai_api_key:
        raise OpenAIUnavailable("OPENAI_API_KEY is not configured")

    context = "\n\n".join(
        f"[{index}] File: {item.document.filename} | Page: {item.chunk.page_number} | Chunk: {item.chunk.id}\n{item.chunk.content}"
        for index, item in enumerate(retrieved, start=1)
    )
    user_prompt = f"""Document context:
{context}

User question:
{message}
"""

    client_kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = OpenAI(**client_kwargs)

    if hasattr(client, "responses"):
        response = client.responses.create(
            model=settings.openai_chat_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.openai_temperature,
        )
        text = getattr(response, "output_text", None)
        if text:
            return text.strip()

    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=settings.openai_temperature,
    )
    return response.choices[0].message.content.strip()


def _citation_dict(item: RetrievedChunk) -> dict:
    return {
        "document_id": item.document.id,
        "filename": item.document.filename,
        "page_number": item.chunk.page_number,
        "chunk_id": item.chunk.id,
        "excerpt": excerpt(item.chunk.content),
    }
